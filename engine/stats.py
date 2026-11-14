"""Statistici de iteme si recomandarea de build, din deadlock-api.com.

Ideea: pentru eroul tau luam win rate-ul fiecarui item pe patch-ul curent, apoi
acelasi lucru filtrat pe fiecare inamic ("meciuri in care in echipa adversa era
Haze"). Cat creste un item fata de cum merge el de obicei, contra unui inamic,
inseamna ca itemul ajuta contra lui.

Win rate-ul brut al itemelor scumpe e umflat (le cumpara cine deja castiga), de
aceea comparam doar in acelasi tier si tragem rezultatele spre medie cand sunt
putine meciuri (shrinkage), ca un item cu 40 de meciuri sa nu para minune.
"""

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

from .assets import API, http_json

CACHE_TTL = 12 * 3600
K_TIER = 300            # cat de tare tragem win rate-ul unui item spre media tier-ului
K_COUNTER = 400         # la fel pentru efectul contra unui inamic
MIN_PICK = 0.03         # sub 3% din meciuri itemul nu intra in build
MIN_MATCHES = 150
WINDOW_DAYS = 14        # mai mult nu ajuta (sute de mii de meciuri) si cererile ies din timp
MIN_DAYS = 4


class Stats:
    def __init__(self, home, log=None):
        self.dir = os.path.join(home, 'cache', 'stats')
        os.makedirs(self.dir, exist_ok=True)
        self.log = log or (lambda *_: None)
        self.badge = None           # filtru de rang (min_average_badge), None = toate
        self._since = None
        # API-ul cere sa nu trimitem multe cereri necache-uite in paralel
        self._gate = threading.Semaphore(2)

    # --- cereri cu cache ----------------------------------------------------------

    def _get(self, path, params, ttl=CACHE_TTL, timeout=60):
        key = hashlib.sha1((path + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:20]
        file = os.path.join(self.dir, key + '.json')
        if os.path.exists(file) and time.time() - os.path.getmtime(file) < ttl:
            with open(file, encoding='utf8') as f:
                return json.load(f)
        last = None
        for attempt in range(3):
            try:
                with self._gate:
                    data = http_json(API + path, params=params, timeout=timeout)
                tmp = file + '.part'
                with open(tmp, 'w', encoding='utf8') as f:
                    json.dump(data, f)
                os.replace(tmp, file)
                return data
            except requests.HTTPError as e:
                last = e
                code = e.response.status_code if e.response is not None else 0
                if code == 504:         # cererea iese din timp: aceeasi cerere pica minute bune
                    break
                wait = e.response.headers.get('Retry-After') if e.response is not None else None
                time.sleep(min(30, float(wait)) if wait and wait.isdigit() else 3 + 4 * attempt)
            except Exception as e:
                last = e
                time.sleep(3 + 4 * attempt)
        if os.path.exists(file):        # mai bine date vechi decat nimic
            with open(file, encoding='utf8') as f:
                return json.load(f)
        raise last

    def since(self):
        """Ultimele WINDOW_DAYS zile, dar nu inainte de patch-ul mare curent (atunci
        s-au schimbat itemele). Daca patch-ul e foarte nou, macar MIN_DAYS zile.
        Rotunjit la miezul noptii UTC: aceleasi cereri toata ziua, deci cache-ul
        lor (si al nostru) se nimereste."""
        day = 24 * 3600
        today = int(time.time()) // day * day
        if self._since and self._since[0] == today:
            return self._since[1]
        since = today - WINDOW_DAYS * day
        try:
            days = self._get('/v1/patches/big-days', {}, ttl=6 * 3600)
            patch = int(datetime.fromisoformat(days[0].replace('Z', '+00:00')).timestamp())
            since = max(since, min(patch // day * day, today - MIN_DAYS * day))
        except Exception:
            pass
        self._since = (today, since)
        return since

    def _filters(self):
        p = {'min_unix_timestamp': self.since(), 'game_mode': 'normal'}
        if self.badge:
            p['min_average_badge'] = self.badge
        return p

    def item_stats(self, hero, enemy=None):
        p = {'hero_id': hero, **self._filters()}
        if enemy:
            p['enemy_hero_ids'] = str(enemy)
        return self._get('/v1/analytics/item-stats', p)

    def hero_stats(self):
        return self._get('/v1/analytics/hero-stats', self._filters())

    def counters(self):
        return self._get('/v1/analytics/hero-counter-stats', self._filters(), timeout=90)

    def imbues(self, hero, ability_names):
        """Pe ce abilitate dau imbue autorii celor mai apreciate build-uri ale eroului.
        Intoarce {item_id: [{'ability', 'name', 'share'}]} (share in procente)."""
        try:
            builds = self._get('/v1/builds', {'hero_id': hero, 'sort_by': 'favorites', 'sort_direction': 'desc',
                                              'limit': 80, 'only_latest': 'true'}, timeout=30)
        except Exception as e:
            self.log(f'builds {hero}: {e}')
            return {}
        counts = {}
        for b in builds:
            seen = set()
            for cat in ((b.get('hero_build') or {}).get('details') or {}).get('mod_categories') or []:
                for m in cat.get('mods') or []:
                    t, iid = m.get('imbue_target_ability_id'), m.get('ability_id')
                    if t and iid and (iid, t) not in seen:      # o data pe build
                        seen.add((iid, t))
                        counts.setdefault(iid, {})
                        counts[iid][t] = counts[iid].get(t, 0) + 1
        out = {}
        for iid, c in counts.items():
            tot = sum(c.values())
            if tot < 3:
                continue
            out[iid] = [{'ability': a, 'name': ability_names.get(a, '?'), 'share': round(100 * n / tot), 'n': tot}
                        for a, n in sorted(c.items(), key=lambda kv: -kv[1])[:2]]
        return out

    # --- recomandarea ---------------------------------------------------------------

    def recommend(self, hero, enemies, items, names, ability_names=None):
        """hero: id-ul tau; enemies: id-uri; items: assets.items; names: {id: nume}."""
        enemies = [e for e in enemies if e and e != hero]
        with ThreadPoolExecutor(4) as pool:
            f_base = pool.submit(self.item_stats, hero)
            f_hero = pool.submit(self.hero_stats)
            f_cnt = pool.submit(self.counters)
            f_en = {e: pool.submit(self.item_stats, hero, e) for e in enemies}
            f_imb = pool.submit(self.imbues, hero, ability_names or {})
            base = f_base.result()
            hs = f_hero.result()
            try:
                cnt = f_cnt.result()
            except Exception:
                cnt = []
            per_enemy = {}
            for e, f in f_en.items():
                try:
                    per_enemy[e] = f.result()
                except Exception as ex:
                    self.log(f'stats {hero} vs {e}: {ex}')
            imbue = f_imb.result()

        h = next((x for x in hs if x['hero_id'] == hero), None)
        hero_n = h['matches'] if h else max((x['matches'] for x in base), default=1)
        hero_wr = h['wins'] / h['matches'] if h and h['matches'] else 0.5
        vs = {}
        for c in cnt:
            if c['hero_id'] == hero and c['enemy_hero_id'] in enemies and c['matches_played']:
                vs[c['enemy_hero_id']] = (c['wins'] / c['matches_played'], c['matches_played'])

        rows = {}
        for r in base:
            it = items.get(r['item_id'])
            if not it or not r['matches']:
                continue
            rows[r['item_id']] = {
                'item': it, 'n': r['matches'], 'wr': r['wins'] / r['matches'],
                'pick': r['matches'] / max(1, hero_n), 'buy': r.get('avg_buy_time_s') or 0,
                'counters': [],
            }

        # media pe tier, ponderata cu meciurile: referinta pentru "bun / slab"
        tier_mean = {}
        for t in (1, 2, 3, 4):
            rs = [r for r in rows.values() if r['item']['tier'] == t and r['n'] >= MIN_MATCHES]
            n = sum(r['n'] for r in rs)
            tier_mean[t] = sum(r['wr'] * r['n'] for r in rs) / n if n else hero_wr
        for r in rows.values():
            m = tier_mean.get(r['item']['tier'], hero_wr)
            r['wr_s'] = (r['wr'] * r['n'] + m * K_TIER) / (r['n'] + K_TIER)
            r['quality'] = r['wr_s'] - m

        # efectul contra fiecarui inamic: cat creste itemul fata de cum merge de obicei
        for e, data in per_enemy.items():
            e_rows = {x['item_id']: x for x in data if x['matches']}
            # referinta: cum merge eroul tau contra lui in general
            e_ref = vs.get(e, (None, 0))[0]
            if e_ref is None:
                tot = sum(x['matches'] for x in e_rows.values()) or 1
                e_ref = sum(x['wins'] for x in e_rows.values()) / tot
            for iid, r in rows.items():
                x = e_rows.get(iid)
                if not x:
                    continue
                lift_e = x['wins'] / x['matches'] - e_ref
                lift_b = r['wr'] - hero_wr
                w = x['matches'] / (x['matches'] + K_COUNTER)
                d = (lift_e - lift_b) * w
                r['counters'].append((d, e, x['matches']))

        for r in rows.values():
            r['counter'] = sum(d for d, _, _ in r['counters'])
            r['score'] = r['quality'] + r['counter']

        def view(r):
            good = sorted([c for c in r['counters'] if c[0] > 0.003], reverse=True)[:2]
            bad = sorted([c for c in r['counters'] if c[0] < -0.008])[:1]
            it = r['item']
            return {
                'id': it['id'], 'name': it['name'], 'slot': it['slot'], 'tier': it['tier'],
                'cost': it['cost'], 'active': it['active'],
                'wr': round(r['wr'] * 100, 1), 'pick': round(r['pick'] * 100, 1),
                'n': r['n'], 'counter': round(r['counter'] * 100, 1),
                'score': round(r['score'] * 100, 2), 'buy_min': round(r['buy'] / 60),
                'from': it.get('upgrades_from') or [], 'imbue': imbue.get(it['id']),
                'vs_good': [{'hero': e, 'name': names.get(e, '?'), 'd': round(d * 100, 1)} for d, e, _ in good],
                'vs_bad': [{'hero': e, 'name': names.get(e, '?'), 'd': round(d * 100, 1)} for d, e, _ in bad],
            }

        usable = [r for r in rows.values() if r['n'] >= MIN_MATCHES and r['pick'] >= MIN_PICK]
        tiers = []
        for t in (1, 2, 3, 4):
            rs = sorted((r for r in usable if r['item']['tier'] == t), key=lambda r: -r['score'])
            tiers.append({'tier': t, 'cost': rs[0]['item']['cost'] if rs else None,
                          'items': [view(r) for r in rs[:5]]})
        counter_picks = sorted((r for r in usable if r['counter'] > 0.012), key=lambda r: -r['counter'])[:5]
        avoid = sorted((r for r in usable if r['pick'] >= 0.12 and r['counter'] < -0.012),
                       key=lambda r: r['counter'])[:3]
        matchups = [{'hero': e, 'name': names.get(e, '?'), 'wr': round(vs[e][0] * 100, 1), 'n': vs[e][1]}
                    for e in enemies if e in vs]
        return {
            'hero': hero, 'hero_name': names.get(hero, '?'), 'hero_wr': round(hero_wr * 100, 1),
            'matches': hero_n, 'since': self.since(), 'enemies': enemies,
            'tiers': tiers, 'counter_picks': [view(r) for r in counter_picks],
            'avoid': [view(r) for r in avoid], 'matchups': matchups,
            'missing': [names.get(e, '?') for e in enemies if e not in per_enemy],
            'pool': [view(r) for r in usable], 'imbue': imbue,
        }


def next_items(rec, owned, items, count=3):
    """Ce sa cumperi acum, din ce ai deja. owned: id-urile itemelor din sloturi.

    - ce ai construit consuma componentele: nu le mai recomandam;
    - tier-ul urca odata cu ce ai: dupa primele iteme nu mai propunem 800-uri;
    - un item care se face din ceva ce ai deja e mai ieftin, deci urca in lista;
    - itemele care contreaza echipa lor urca si ele."""
    if not rec:
        return []
    owned = set(owned)
    used = set(owned)
    for iid in owned:
        used.update((items.get(iid) or {}).get('upgrades_from') or [])
    tiers = [items[i]['tier'] for i in owned if i in items]
    t_max = max(tiers, default=0)
    n = len(owned)
    if t_max <= 1 and n < 4:
        allowed = {1, 2}
    else:
        allowed = {max(2, t_max - 1), t_max, min(4, t_max + 1)}
        if n < 3:
            allowed.add(1)
    t_low = min(allowed)
    best = []
    for it in rec.get('pool', []):
        if it['id'] in used or it['tier'] not in allowed:
            continue
        base = [c for c in it.get('from') or [] if c in owned]
        pri = it['score'] + it['counter'] + 0.04 * it['pick'] - 0.8 * (it['tier'] - t_low) + (1.5 if base else 0)
        why = []
        if it['vs_good'] and it['counter'] > 0.5:
            why.append('contra ' + ', '.join(v['name'] for v in it['vs_good']))
        if base:
            why.append('se face din ' + ', '.join(items[c]['name'] for c in base if c in items))
        if not why:
            why.append(f"luat in {it['pick']:.0f}% din meciuri, {it['wr']:.1f}% win rate")
        best.append((pri, {**it, 'why': '; '.join(why)}))
    best.sort(key=lambda p: -p[0])
    return [b for _, b in best[:count]]
