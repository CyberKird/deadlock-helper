"""Motorul Deadlock Helper.

Ruleaza ca proces copil al interfetei (ui/, Electron). Scrie starea pe stdout,
cate un JSON pe linie, si primeste comenzi pe stdin. Fara interfata:
  python app.py --selfcheck     verifica datele, sabloanele si cadrele de test
"""

import json
import os
import queue
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from engine import bug_report                         # noqa: E402
from engine.assets import Assets                      # noqa: E402
from engine.game import Grabber, dpi_aware, find_game, show_in_taskbar  # noqa: E402
from engine import hud                                # noqa: E402
from engine.stats import Stats, next_items            # noqa: E402
from engine.vision import TopBar, Tracker, load_templates, slot_centers   # noqa: E402

import cv2                                            # noqa: E402
cv2.setNumThreads(2)        # jocul are nevoie de procesor mai mult decat noi

HOME = os.environ.get('DLH_HOME') or os.path.join(os.environ.get('APPDATA', ROOT), 'deadlock-helper')
os.makedirs(HOME, exist_ok=True)
LOG = os.path.join(HOME, 'engine.log')
VERSION = os.environ.get('DLH_VERSION', 'dev')

SCAN_EVERY = 2.5        # s intre citiri cat cautam eroii
VERIFY_EVERY = 8.0      # s intre verificari dupa ce i-am gasit pe toti
IDLE_EVERY = 3.0        # s intre verificari cand jocul nu ruleaza
BOTTOM_EVERY = 3.0      # s intre citirile itemelor tale
BOTTOM = hud.BOTTOM


def log(*a):
    try:
        with open(LOG, 'a', encoding='utf8') as f:
            f.write(time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a) + '\n')
    except OSError:
        pass


def emit(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + '\n')
    sys.stdout.flush()


class Engine:
    def __init__(self):
        self.assets = Assets(HOME)
        self.stats = Stats(HOME, log=log)
        self.cmds = queue.Queue()
        self.tracker = Tracker()
        self.topbar = None
        self.view = 'loading'
        self.game = None
        self.rec = None
        self.rec_key = None
        self.rec_busy = False
        self.rec_error = None
        self.manual = None          # {'hero': id, 'enemies': [...]} cand alegi de mana
        self.lang = 'ro' if os.environ.get('DLH_LANG') == 'ro' else 'en'
        self.bad_reads = 0
        self.last_top = 0.0
        self.own_reader = None
        self.inventory = None
        self.own_hero = None
        self.own_votes = {}
        self.owned = {}             # slot -> item_id, din HUD
        self.inv_pending = None
        self.last_band = None
        self.last_x = None
        self.empty_reads = 0
        self.last_seen = 0.0
        self.settings_path = os.path.join(HOME, 'engine_settings.json')
        self.settings = self._load_settings()
        self.stats.badge = self.settings.get('badge')

    def _load_settings(self):
        try:
            with open(self.settings_path, encoding='utf8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        try:
            with open(self.settings_path, 'w', encoding='utf8') as f:
                json.dump(self.settings, f)
        except OSError:
            pass

    # --- pornire ------------------------------------------------------------------

    def boot(self):
        self.assets.load()
        missing = self.assets.fetch_images()
        if missing:
            log('carduri lipsa:', missing)
        self.topbar = TopBar(load_templates(self.assets, os.path.join(HOME, 'learned')))
        abil = {hid: [self.assets.image_path('abil', a['id']) for a in h.get('abilities', [])]
                for hid, h in self.assets.heroes.items()}
        self.own_reader = hud.OwnHero({k: v for k, v in abil.items() if all(os.path.exists(p) for p in v)})
        self.inventory = hud.Inventory({iid: self.assets.image_path('item', iid) for iid in self.assets.items
                                        if os.path.exists(self.assets.image_path('item', iid))})
        emit({'t': 'hello', 'img': self.assets.img, 'home': HOME,
              'heroes': sorted(({'id': h['id'], 'name': h['name']} for h in self.assets.heroes.values()),
                               key=lambda h: h['name'])})

    # --- comenzi de la interfata -------------------------------------------------------

    def handle(self, c):
        cmd = c.get('cmd')
        tr = self.tracker
        if cmd == 'set_slot':
            slot, hero = int(c['slot']), c.get('hero')
            if 0 <= slot < 12:
                if hero:
                    tr.manual[slot] = int(hero)
                    self.learn(slot, int(hero))
                else:
                    tr.manual.pop(slot, None)
        elif cmd == 'set_own':
            slot = c.get('slot')
            tr.manual_own = int(slot) if slot is not None else None
        elif cmd == 'reset':
            self.new_match()
        elif cmd == 'manual':
            hero = c.get('hero')
            enemies = [int(e) for e in c.get('enemies') or [] if e]
            self.manual = {'hero': int(hero), 'enemies': enemies[:6]} if hero else None
        elif cmd == 'badge':
            self.settings['badge'] = c.get('value') or None
            self.stats.badge = self.settings['badge']
            self._save_settings()
            self.rec_key = None
        elif cmd == 'refresh':
            self.rec_key = None
        elif cmd == 'diag':
            emit({'t': 'reply', 'id': c.get('id'),
                  'text': bug_report.build_diagnostics(VERSION, HOME, self)})
        elif cmd == 'report':
            def work(msg=c):
                problem = bug_report.validate(msg.get('desc', ''), msg.get('email', ''), self.lang)
                if problem:
                    ok, text, kind = False, problem, 'validate'
                else:
                    ok, text = bug_report.send(msg.get('desc', ''), msg.get('email', ''), msg.get('diag', ''),
                                               VERSION, lang=self.lang)
                    kind = 'send'
                emit({'t': 'reply', 'id': msg.get('id'), 'ok': ok, 'text': text, 'kind': kind})
            threading.Thread(target=work, daemon=True).start()
        elif cmd == 'lang':
            self.lang = 'ro' if c.get('value') == 'ro' else 'en'
        elif cmd == 'mailto':
            bug_report.mailto(c.get('desc', ''), c.get('diag', ''), VERSION)

    def learn(self, slot, hero):
        """Ai corectat un slot: tinem minte cum arata portretul pe ecranul tau
        (skin, erou nou), ca data viitoare sa-l recunoastem singuri."""
        if not self.last_band or self.view != 'match':
            return
        band, cx = self.last_band
        x = self.last_x[slot] if self.last_x and self.last_x[slot] else slot_centers(cx)[slot]
        if self.topbar.t.learn(hero, band, x, self.topbar.scale):
            log(f'invatat: slot {slot} = erou {hero}')

    # --- citirea HUD-ului ----------------------------------------------------------------

    def scan(self, grabber):
        fake = os.environ.get('DLH_FAKE_FRAME')     # test: un cadru salvat in loc de joc
        if fake:
            import cv2
            img = cv2.imread(fake)
            g = {'rect': [0, 0, img.shape[1], img.shape[0]], 'running': True, 'foreground': True, 'img': img}
        else:
            g = find_game()
        self.game = g
        if not g or not g.get('rect'):
            if self.view in ('match', 'searching') and time.time() - self.last_seen > 20:
                self.new_match()
            self.view = 'idle'
            return IDLE_EVERY
        if g.get('minimized') or not g.get('foreground'):
            return IDLE_EVERY       # alt-tab: pe ecran nu e jocul, nu are rost sa citim
        x0, y0, x1, y1 = g['rect']
        gh, gw = y1 - y0, x1 - x0
        now = time.time()
        tr = self.tracker
        known = {i: h for i, h in enumerate(tr.locked) if h}
        complete = tr.complete() and len(known) == 12
        wait = SCAN_EVERY
        if not complete or now - self.last_top >= VERIFY_EVERY:
            self.last_top = now
            frame = g['img'][:int(gh * 0.125)] if 'img' in g else grabber.top(g['rect'])
            band, cx = TopBar.strip(frame, gw / 2, game_h=gh)
            self.last_band = (band, cx)
            if complete:
                self.verify_top(band, cx, known)
            else:
                slots = self.topbar.read(band, cx)
                self.last_x = [s['x'] if s else None for s in slots]
                seen = tr.update(slots)
                if seen >= 4:
                    self.last_seen = now
                    self.view = 'match'
                    self.empty_reads = 0
                else:
                    if self.view != 'match' or now - self.last_seen > 60:
                        self.view = 'searching'
                    # fara bara de sus (meniu, hideout, ecran de incarcare): citim tot mai rar
                    self.empty_reads += 1
                    wait = min(SCAN_EVERY * (1 + self.empty_reads // 3), 10.0)
        if self.view == 'match':
            bottom = g['img'][int(gh * (1 - BOTTOM)):] if 'img' in g else grabber.bottom(g['rect'], BOTTOM)
            self.read_bottom(bottom, gw, gh)
            wait = min(wait, BOTTOM_EVERY)
        return wait

    def verify_top(self, band, cx, known):
        """Verificare ieftina: aceiasi eroi, acelasi meci?"""
        slots = self.topbar.read(band, cx, only=known)
        if sum(1 for s in slots if s and s['raw'] > 0.45) >= 6:
            self.bad_reads = 0
            self.last_seen = time.time()
            self.view = 'match'
            return
        self.bad_reads += 1
        if self.bad_reads >= 3:     # HUD ascuns (meniu, hideout) sau alt meci
            full = self.topbar.read(band, cx)
            if sum(1 for s in full if s and s['raw'] > 0.7) >= 6:
                log('meci nou: eroi diferiti')
                self.new_match()
            self.bad_reads = 0

    def read_bottom(self, bottom, gw, gh):
        img, top = hud.normalize(bottom, gh)
        cx = gw * hud.REF_H / gh / 2
        tr = self.tracker
        # eroul tau, dupa abilitati: o data confirmat, nu se mai schimba in meciul asta
        if self.own_hero is None and self.own_reader:
            locked = [h for h in tr.heroes() if h]
            cands = set(locked) if len(locked) >= 8 else None
            res = self.own_reader.read(img, top, cx, cands)
            if len(res) >= 2 and res[0][0] > 0.65 and res[0][0] - res[1][0] > 0.12:
                h = res[0][1]
                self.own_votes[h] = self.own_votes.get(h, 0) + 1
                if self.own_votes[h] >= 2:
                    self.own_hero = h
                    log(f'eroul tau (dupa abilitati): {h}')
        heroes = tr.heroes()
        tr.ability_own = heroes.index(self.own_hero) if self.own_hero in heroes else None
        # itemele tale: acceptam o schimbare doar daca doua citiri la rand spun la fel
        if self.inventory:
            got = {slot: iid for slot, iid, _ in self.inventory.read(img, top, self.owned)}
            if got == self.inv_pending or (got and set(got.values()) > set(self.owned.values())):
                self.owned = got
            self.inv_pending = got

    def new_match(self):
        self.tracker.reset()
        self.rec = self.rec_key = None
        self.own_hero = None
        self.own_votes = {}
        self.owned = {}
        self.inv_pending = None

    # --- echipe si recomandare ------------------------------------------------------------

    def teams(self):
        heroes = self.tracker.heroes()
        own = self.tracker.own_slot()
        if own is None:
            return heroes, None, None, []
        mine = range(0, 6) if own < 6 else range(6, 12)
        theirs = range(6, 12) if own < 6 else range(0, 6)
        return heroes, own, heroes[own], [heroes[i] for i in theirs if heroes[i]]

    def want_rec(self):
        if self.manual:
            return self.manual['hero'], self.manual['enemies']
        heroes, own, me, enemies = self.teams()
        if me and len(enemies) >= 4:
            return me, enemies
        return None, []

    def maybe_recommend(self):
        hero, enemies = self.want_rec()
        if not hero:
            return
        key = (hero, tuple(sorted(enemies)), self.stats.badge)
        if key == self.rec_key or self.rec_busy:
            return
        self.rec_key = key
        self.rec_busy = True
        self.rec_error = None
        names = {h: v['name'] for h, v in self.assets.heroes.items()}

        def work():
            try:
                rec = self.stats.recommend(hero, list(enemies), self.assets.items, names,
                                           self.assets.ability_names)
                if self.rec_key == key:
                    self.rec = rec
            except Exception as e:
                log('recomandare:', repr(e))
                self.rec_error = 'stats_down'
                self.rec_key = None
                time.sleep(20)
            finally:
                self.rec_busy = False
                self.push()

        threading.Thread(target=work, daemon=True).start()

    def push(self):
        heroes, own, me, enemies = self.teams()
        names = {h: v['name'] for h, v in self.assets.heroes.items()}
        slots = []
        for i, h in enumerate(heroes):
            side = None if own is None else ('own' if (i < 6) == (own < 6) else 'enemy')
            slots.append({'slot': i, 'hero': h, 'name': names.get(h), 'side': side,
                          'manual': i in self.tracker.manual, 'you': i == own})
        g = self.game or {}
        items = self.assets.items
        owned = []
        imb = (self.rec or {}).get('imbue') or {}
        for slot, iid in sorted(self.owned.items()):
            it = items.get(iid)
            if it:
                owned.append({'id': iid, 'name': it['name'], 'slot': it['slot'], 'tier': it['tier'],
                              'imbue': imb.get(iid) if it.get('imbue') else None})
        nxt = next_items(self.rec, list(self.owned.values()), items) if self.rec else []
        emit({'t': 'state', 'owned': owned, 'next': nxt, 'own_hero': self.own_hero, 'view': 'manual' if self.manual and self.view != 'match' else self.view,
              'game': {'running': bool(g), 'rect': None if 'img' in g else g.get('rect'),
                       'foreground': g.get('foreground', False)},
              'slots': slots, 'own': own, 'rec': self.rec, 'busy': self.rec_busy,
              'error': self.rec_error, 'manual': self.manual, 'badge': self.stats.badge})

    # --- bucla -------------------------------------------------------------------------

    def run(self):
        dpi_aware()
        threading.Thread(target=self._stdin, daemon=True).start()
        try:
            self.boot()
        except Exception as e:
            log('boot:', traceback.format_exc())
            emit({'t': 'error', 'text': f'nu pot incarca datele: {e}'})
        grabber = Grabber()
        next_scan = 0.0
        last_push = None
        while True:
            try:
                c = self.cmds.get(timeout=0.25)
                if c is None or c.get('cmd') == 'quit':
                    break
                self.handle(c)
                last_push = None
            except queue.Empty:
                pass
            except Exception:
                log('comanda:', traceback.format_exc())
            now = time.time()
            if self.topbar and now >= next_scan:
                try:
                    next_scan = now + self.scan(grabber)
                except Exception:
                    log('scan:', traceback.format_exc())
                    next_scan = now + 5
            if self.topbar:
                self.maybe_recommend()
            snap = json.dumps([self.view, self.tracker.heroes(), self.tracker.own_slot(), self.rec_key,
                               self.rec_busy, self.rec_error, bool(self.game), (self.game or {}).get('rect'),
                               self.manual, id(self.rec), sorted(self.owned.items()), self.own_hero])
            if snap != last_push:
                last_push = snap
                self.push()
        grabber.close()

    def _stdin(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
            except ValueError:
                continue
            if c.get('cmd') == 'taskbar':        # imediat, nu dupa incarcarea datelor
                show_in_taskbar(c.get('hwnd'), os.environ.get('DLH_UI_PID'))
            else:
                self.cmds.put(c)
        self.cmds.put(None)         # interfata s-a inchis: iesim si noi


def selfcheck():
    eng = Engine()
    eng.assets.load()
    missing = eng.assets.fetch_images()
    print(f'eroi {len(eng.assets.heroes)}, iteme {len(eng.assets.items)}, carduri lipsa: {missing or "niciunul"}')
    tpl = load_templates(eng.assets)
    print(f'sabloane: {len(tpl.ids)}')
    frames = os.path.join(ROOT, 'tests', 'frames')
    if os.path.isdir(frames):
        import subprocess
        subprocess.run([sys.executable, os.path.join(ROOT, 'tests', 'test_vision.py'), HOME])
    print('since', eng.stats.since())
    return 0


if __name__ == '__main__':
    if '--selfcheck' in sys.argv:
        sys.exit(selfcheck())
    Engine().run()
