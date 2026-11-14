"""Recunoasterea eroilor din bara de sus a HUD-ului.

Cum deseneaza jocul bara (din panorama/styles/citadel_hud_top_bar.vcss si
hero_badge.vcss, in unitati de 1080p, scalate cu inaltimea ecranului):
  - 6 sloturi stanga, 6 dreapta, simetrice fata de mijloc, cam 88 px intre ele;
  - in fiecare slot e card-ul eroului (280x380) scalat "contain" la 80% din
    88 px = 70.4 px latime, taiat cu o masca in forma de U (dreptunghi sus,
    semicerc jos), deci capul iese deasupra cercului colorat al echipei;
  - un erou mort e desaturat si intunecat, de aceea comparam si in gri.

Potrivire de sablon (TM_CCOEFF_NORMED cu masca) pe fiecare slot, in doi pasi:
intai la jumatate de rezolutie pe toti eroii, apoi la rezolutie plina doar pe
primii candidati. Pozitia teoretica a slotului e doar punctul de plecare: o
fereastra de cautare acopera HUD-uri decalate cu cativa pixeli.
"""

import os
import time

import cv2
import numpy as np

REF_H = 1080
SLOT_FIRST = 142.0      # px de la mijloc la centrul slotului cel mai apropiat (1080p)
SLOT_STEP = 87.5        # px intre sloturi
CARD_W = 70.4           # latimea card-ului in slot
STRIP_H = 128           # cat din partea de sus a ecranului citim (1080p)
SEARCH = 24             # cat poate fi decalat un slot fata de pozitia teoretica
SCALES = (0.96, 1.0, 1.04)
PAD_TOP = 24            # card-ul poate iesi putin peste marginea ecranului
CANDIDATES = 6          # cati eroi trec din pasul grosier in cel fin


def u_mask(h, w):
    """Masca jocului: dreptunghi sus, semicerc cu diametrul latimii jos."""
    r = w / 2.0
    cy = h - r
    ys, xs = np.mgrid[0:h, 0:w]
    inside = (ys <= cy) | ((xs + 0.5 - r) ** 2 + (ys + 0.5 - cy) ** 2 <= r * r)
    return inside.astype(np.float32)


def slot_centers(cx):
    """Centrele celor 12 sloturi, in ordinea de pe ecran (stanga -> dreapta)."""
    left = [cx - (SLOT_FIRST + i * SLOT_STEP) for i in range(5, -1, -1)]
    right = [cx + (SLOT_FIRST + i * SLOT_STEP) for i in range(6)]
    return left + right


def _prep(im, w):
    h = int(round(w * im.shape[0] / im.shape[1]))
    rgba = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0 * u_mask(h, w)
    m = (alpha > 0.5).astype(np.uint8)
    bgr = np.ascontiguousarray(rgba[:, :, :3])
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return bgr, gray, cv2.merge([m, m, m]), m


class Templates:
    """Sabloanele: card-ul fiecarui erou (la 3 scale) plus portretele invatate de
    pe ecranul tau cand corectezi un slot (skin-uri, eroi noi). Cele invatate sunt
    deja la scara ecranului, deci merg la orice scala."""

    def __init__(self, cards, learned_dir=None):
        """cards: {hero_id: path catre card png RGBA}."""
        self.fine = {s: {} for s in SCALES}
        self.coarse = {s: {} for s in SCALES}
        self.learned = {}           # hero_id -> [(fin, grosier)]
        self.learned_dir = learned_dir
        for hid, path in cards.items():
            im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if im is None or im.ndim != 3 or im.shape[2] != 4:
                continue
            if (im[:, :, 3] > 128).mean() > 0.95:      # fara transparenta: nu e un card valid
                continue
            for s in SCALES:
                self.fine[s][hid] = _prep(im, int(round(CARD_W * s)))
                self.coarse[s][hid] = _prep(im, int(round(CARD_W * s / 2)))
        self.ids = sorted(self.fine[1.0])
        if learned_dir and os.path.isdir(learned_dir):
            for f in sorted(os.listdir(learned_dir)):
                try:
                    hid = int(f.split('_')[0])
                except ValueError:
                    continue
                im = cv2.imread(os.path.join(learned_dir, f))
                if im is not None and hid in self.fine[1.0]:
                    self._add(hid, im)

    @staticmethod
    def _disk(h, w):
        """Doar cercul colorat de sub cap: in afara lui se vede harta, care se schimba."""
        r = w / 2.0
        ys, xs = np.mgrid[0:h, 0:w]
        m = ((xs + 0.5 - r) ** 2 + (ys + 0.5 - (h - r)) ** 2 <= (r - 3) ** 2).astype(np.uint8)
        return m

    def _add(self, hid, bgr):
        out = []
        for img in (bgr, cv2.resize(bgr, (bgr.shape[1] // 2, bgr.shape[0] // 2), interpolation=cv2.INTER_AREA)):
            m = self._disk(*img.shape[:2])
            img = np.ascontiguousarray(img)
            out.append((img, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.merge([m, m, m]), m))
        self.learned.setdefault(hid, []).append(tuple(out))
        self.learned[hid] = self.learned[hid][-3:]

    def learn(self, hid, band, x, scale):
        """Tine minte cum arata slotul de la x (banda normalizata) ca eroul hid."""
        w = int(round(CARD_W * (scale or 1.0)))
        h = int(round(w * 380 / 280))
        x0 = int(round(x - w / 2))
        crop = band[PAD_TOP:PAD_TOP + h, x0:x0 + w]
        if crop.shape[:2] != (h, w) or hid not in self.fine[1.0]:
            return False
        self._add(hid, crop.copy())
        if self.learned_dir:
            os.makedirs(self.learned_dir, exist_ok=True)
            mine = sorted(f for f in os.listdir(self.learned_dir) if f.startswith(f'{hid}_'))
            for old in mine[:-2]:               # pastram ultimele 3
                try:
                    os.remove(os.path.join(self.learned_dir, old))
                except OSError:
                    pass
            cv2.imwrite(os.path.join(self.learned_dir, f'{hid}_{int(time.time())}.png'), crop)
        return True

    def variants(self, s, hid, coarse=False):
        k = 1 if coarse else 0
        base = (self.coarse if coarse else self.fine)[s].get(hid)
        out = [base] if base else []
        return out + [v[k] for v in self.learned.get(hid, [])]


def _score(img, tpl, mask):
    r = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED, mask=mask)
    r[~np.isfinite(r)] = -1
    _, mx, _, loc = cv2.minMaxLoc(r)
    return mx, loc


class TopBar:
    def __init__(self, templates):
        self.t = templates
        self.scale = None           # scala gasita la prima citire buna, apoi fixata

    @staticmethod
    def strip(frame, cx, game_h=None):
        """Normalizeaza o captura a jocului (BGR, de la marginea de sus a jocului)
        la 1080p si taie banda de sus. cx: mijlocul jocului in pixeli ai capturii;
        game_h: inaltimea jocului, daca frame e doar banda de sus.
        Intoarce (banda, cx in banda)."""
        k = REF_H / (game_h or frame.shape[0])
        h = min(frame.shape[0], int(round(STRIP_H / k)))
        band = frame[:h]
        if abs(k - 1) > 1e-3:
            band = cv2.resize(band, None, fx=k, fy=k,
                              interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
        band = cv2.copyMakeBorder(band, PAD_TOP, 0, 0, 0, cv2.BORDER_REPLICATE)
        return band, cx * k

    def read(self, band, cx, only=None):
        """Intoarce 12 elemente (None daca slotul iese din imagine):
        {x, scores: [(scor, hero_id)...] descrescator, raw, color, own}.
        only: {slot: hero_id} = verifica doar eroii deja stiuti (ieftin)."""
        scales = [self.scale] if self.scale else list(SCALES)
        gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(band, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
        raw = []
        for i, x in enumerate(slot_centers(cx)):
            x0 = int(round(x - CARD_W / 2 - SEARCH))
            x1 = int(round(x + CARD_W / 2 + SEARCH))
            if x0 < 0 or x1 > band.shape[1]:
                raw.append(None)
                continue
            if only is not None:
                cands = [only[i]] if only.get(i) in self.t.ids else []
            else:
                cands = self._coarse(small, x0, x1, scales)
            best = {}
            for s in scales:
                for hid in cands:
                    for bgr, g, m3, m1 in self.t.variants(s, hid):
                        h = bgr.shape[0]
                        y0, y1 = max(0, PAD_TOP - 14), min(band.shape[0], PAD_TOP + h + 14)
                        crop = band[y0:y1, x0:x1]
                        if h > crop.shape[0] or bgr.shape[1] > crop.shape[1]:
                            continue
                        c, loc = _score(crop, bgr, m3)
                        gs, _ = _score(gray[y0:y1, x0:x1], g, m1)
                        # culoarea separa eroii, griul tine cand eroul e mort (desaturat)
                        sc = max(c, gs - 0.06)
                        if sc > best.get(hid, (-2,))[0]:
                            best[hid] = (sc, s, x0 + loc[0] + bgr.shape[1] / 2)
            raw.append(best)
        out, votes = [], {}
        for r in raw:
            if not r:
                out.append(None)
                continue
            ranked = sorted(((v[0], hid) for hid, v in r.items()), reverse=True)
            top = r[ranked[0][1]]
            votes[top[1]] = votes.get(top[1], 0) + ranked[0][0]
            out.append({'x': top[2], 'scores': ranked[:5], 'raw': ranked[0][0],
                        'color': self._team_color(hsv, top[2])})
        # scala: o fixam doar cand bara e clar citita (multe sloturi sigure)
        if not self.scale and only is None and votes:
            if sum(1 for o in out if o and o['raw'] > 0.75) >= 8:
                self.scale = max(votes, key=votes.get)
        self._mark_own(out)
        return out

    def _coarse(self, small, x0, x1, scales):
        """Primii candidati pentru un slot, la jumatate de rezolutie, doar in culoare.
        Scade nivelul de fond al fiecarui card (unele se potrivesc putin cu orice)."""
        a, b = x0 // 2, (x1 + 1) // 2
        res = {}
        for s in scales:
            for hid in self.t.ids:
                for bgr, _, m3, _ in self.t.variants(s, hid, coarse=True):
                    h = bgr.shape[0]
                    y0, y1 = max(0, PAD_TOP // 2 - 7), min(small.shape[0], PAD_TOP // 2 + h + 7)
                    crop = small[y0:y1, a:b]
                    if h > crop.shape[0] or bgr.shape[1] > crop.shape[1]:
                        continue
                    c, _ = _score(crop, bgr, m3)
                    res[hid] = max(res.get(hid, -2), c)
        return [hid for _, hid in sorted(((v, k) for k, v in res.items()), reverse=True)[:CANDIDATES]]

    @staticmethod
    def _team_color(hsv, x):
        """Cat din fundalul de langa cap are culoarea echipei. Slotul tau are un
        fundal inalt in culoarea echipei (coin_background_selected), celelalte
        doar cercul de jos. Culoarea echipei o luam din casuta cu nivelul, sub cerc."""
        xi = int(round(x))
        box = hsv[PAD_TOP + 100:PAD_TOP + 112, max(0, xi - 8):xi + 8].reshape(-1, 3)
        box = box[(box[:, 1] > 80) & (box[:, 2] > 90)]
        if len(box) < 20:
            return 0.0
        hue = float(np.median(box[:, 0]))
        y0, y1 = PAD_TOP + 4, PAD_TOP + 34
        parts = []
        for dx0, dx1 in ((-37, -29), (29, 37)):
            a, b = xi + dx0, xi + dx1
            if a < 0 or b > hsv.shape[1]:
                continue
            p = hsv[y0:y1, a:b].reshape(-1, 3).astype(np.int16)
            dh = np.abs(p[:, 0] - hue)
            dh = np.minimum(dh, 180 - dh)
            parts.append(((dh < 12) & (p[:, 1] > 50) & (p[:, 2] > 90)).mean())
        return float(np.mean(parts)) if parts else 0.0

    @staticmethod
    def _mark_own(out):
        for o in out:
            if o:
                o['own'] = False
        vals = sorted(((o['color'], i) for i, o in enumerate(out) if o), reverse=True)
        if len(vals) < 2:
            return
        (c1, i1), (c2, _) = vals[0], vals[1]
        if c1 > 0.35 and c1 - c2 > 0.2:
            out[i1]['own'] = True


class Tracker:
    """Voturi pe mai multe cadre, ca un cadru prost (explozie, ecran de moarte,
    meniu deschis) sa nu schimbe eroii. Un slot se fixeaza cand acelasi erou
    castiga de cateva ori cu marja buna."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.votes = [dict() for _ in range(12)]
        self.locked = [None] * 12
        self.own = {}
        self.manual = {}            # slot -> hero_id ales de user (castiga mereu)
        self.manual_own = None      # slotul tau, ales de user

    def update(self, slots):
        """Intoarce cate sloturi au fost citite sigur in cadrul asta."""
        seen = 0
        for i, s in enumerate(slots):
            if not s or not s['scores']:
                continue
            s1, h1 = s['scores'][0]
            s2 = s['scores'][1][0] if len(s['scores']) > 1 else 0.0
            if s1 < 0.5 or s1 - s2 < 0.1:
                continue
            seen += 1
            v = self.votes[i]
            for k in list(v):
                v[k] *= 0.85
            v[h1] = v.get(h1, 0) + (s1 - s2)
            lead = sorted(v.items(), key=lambda kv: -kv[1])
            if lead[0][1] > 0.5 and (len(lead) == 1 or lead[0][1] > 2 * lead[1][1]):
                self.locked[i] = lead[0][0]
            if s.get('own'):
                self.own[i] = self.own.get(i, 0) + 1
        return seen

    def heroes(self):
        return [self.manual.get(i, self.locked[i]) for i in range(12)]

    def complete(self):
        return all(h is not None for h in self.heroes())

    def own_slot(self):
        if self.manual_own is not None:
            return self.manual_own
        if not self.own:
            return None
        i, n = max(self.own.items(), key=lambda kv: kv[1])
        return i if n >= 2 else None


def load_templates(assets, learned_dir=None):
    cards = {hid: assets.image_path('card', hid) for hid in assets.heroes}
    return Templates({k: v for k, v in cards.items() if os.path.exists(v)}, learned_dir)
