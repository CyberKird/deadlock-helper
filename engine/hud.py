"""Partea de jos a HUD-ului: abilitatile (spun ce erou esti) si itemele tale.

Pozitii masurate pe HUD-ul real (4K, scalat la 1080p): HUD-ul se scaleaza cu
inaltimea ecranului, abilitatile sunt centrate, itemele ancorate in stanga.
  - 4 abilitati pe un rand, centre la x = mijloc -111.5 / -37.5 / +36.5 / +111,
    y = 1027; glifa alba (sau gri, daca nu e deblocata) pe un cerc;
  - itemele: 2 randuri x 6, colt stanga-sus (25, 945), pas 61.2 x 60, latura 54;
    in slot e exact imaginea de magazin a itemului (shop_image).
"""

import cv2
import numpy as np

REF_H = 1080
BOTTOM = 0.16                   # cat din partea de jos a ecranului capturam
AB_X = (-111.5, -37.5, 36.5, 111.0)
AB_Y = 1027
AB_SIZES = (36, 40, 44, 48)
AB_LIFT = 24
INV_X0, INV_Y0, INV_DX, INV_DY, INV_S = 25.0, 945.0, 61.2, 60.0, 54
INV_ROWS, INV_COLS = 2, 6
CORE = 0.62                     # din imaginea itemului comparam doar mijlocul (fara colturi si tier)


def normalize(band, game_h):
    """Banda de jos (BGR) -> scara 1080p. Intoarce (imagine, y-ul de sus in 1080p)."""
    k = REF_H / game_h
    img = cv2.resize(band, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
    return img, REF_H - img.shape[0]


class OwnHero:
    """Eroul tau, dupa glifele celor 4 abilitati din mijlocul HUD-ului de jos."""

    def __init__(self, abilities):
        """abilities: {hero_id: [cale png RGBA x 4]} (signature1..4)."""
        self.t = {}
        for hid, paths in abilities.items():
            if len(paths) != 4:
                continue
            per = []
            for p in paths:
                im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
                if im is None or im.ndim != 3 or im.shape[2] != 4:
                    per = None
                    break
                per.append([cv2.resize(im[:, :, 3], (s, s), interpolation=cv2.INTER_AREA) for s in AB_SIZES])
            if per:
                self.t[hid] = per

    def read(self, img, top, cx, candidates=None):
        """Intoarce [(scor, hero_id)] descrescator. Glifa e alba pe gri (blocata) sau
        neagra pe alb (deblocata): comparam forma, deci luam si corelatia negativa."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        crops = []
        for dx in AB_X:
            x, y = int(round(cx + dx)), int(round(AB_Y - top))
            # bara urca putin cand ai puncte de abilitate de pus: cautam si mai sus
            c = gray[max(0, y - 34 - AB_LIFT):y + 34, max(0, x - 34):x + 34]
            crops.append(c if c.shape == (68 + AB_LIFT, 68) else None)
        if any(c is None for c in crops):
            return []
        out = []
        for hid, per in self.t.items():
            if candidates and hid not in candidates:
                continue
            got = []
            for crop, sizes in zip(crops, per):
                best = 0.0
                for t in sizes:
                    r = cv2.matchTemplate(crop, t, cv2.TM_CCOEFF_NORMED)
                    best = max(best, float(r.max()), float(-r.min()))
                got.append(best)
            # abilitatile neinvatate sunt aproape transparente: conteaza cele mai clare doua
            got.sort(reverse=True)
            out.append(((got[0] + got[1]) / 2, hid))
        out.sort(reverse=True)
        return out


class Inventory:
    """Itemele din cele 12 sloturi, comparate cu imaginile de magazin."""

    def __init__(self, items):
        """items: {item_id: cale png}."""
        k = int(round(INV_S * CORE))
        self.core = k
        self.t = []
        for iid, p in items.items():
            im = cv2.imread(p)
            if im is None:
                continue
            full = cv2.resize(im, (INV_S, INV_S), interpolation=cv2.INTER_AREA)
            o = (INV_S - k) // 2
            self.t.append((iid, np.ascontiguousarray(full[o:o + k, o:o + k])))

    @staticmethod
    def _empty(tile):
        """Slot gol: patrat intunecat, semitransparent peste joc. Un item are fundal deschis."""
        hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
        # gol = gri inchis si spalacit; unele iteme au fundal inchis, dar colorat (mov, verde)
        return float(np.median(hsv[:, :, 2])) < 110 and float(np.median(hsv[:, :, 1])) < 60

    def read(self, img, top, known=None):
        """Intoarce lista de (slot, item_id, scor) pentru sloturile ocupate.
        known: {slot: item_id} de la citirea trecuta: daca inca se potriveste, nu mai cautam."""
        out = []
        pad = 5
        for r in range(INV_ROWS):
            for c in range(INV_COLS):
                slot = r * INV_COLS + c
                x0 = int(round(INV_X0 + c * INV_DX))
                y0 = int(round(INV_Y0 + r * INV_DY - top))
                tile = img[max(0, y0 - pad):y0 + INV_S + pad, max(0, x0 - pad):x0 + INV_S + pad]
                if tile.shape[0] < INV_S or tile.shape[1] < INV_S:
                    continue
                inner = tile[pad + 8:pad + INV_S - 8, pad + 8:pad + INV_S - 8]
                if self._empty(inner):
                    continue
                prev = (known or {}).get(slot)
                if prev:
                    t = next((t for iid, t in self.t if iid == prev), None)
                    if t is not None:
                        s = float(cv2.matchTemplate(tile, t, cv2.TM_CCOEFF_NORMED).max())
                        if s > 0.75:
                            out.append((slot, prev, s))
                            continue
                best = (0.0, None)
                for iid, t in self.t:
                    s = float(cv2.matchTemplate(tile, t, cv2.TM_CCOEFF_NORMED).max())
                    if s > best[0]:
                        best = (s, iid)
                if best[1] and best[0] > 0.78:      # un item real iese 0.85+, un slot gol ~0.6
                    out.append((slot, best[1], best[0]))
        return out
