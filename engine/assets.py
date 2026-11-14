"""Eroii si itemele jocului, luate din API-ul public deadlock-api.com.

Totul se tine pe disc in HOME/cache: lista de eroi si de iteme se reimprospateaza
o data pe zi, imaginile (card-ul eroului pentru recunoastere, iconitele pentru
panou) se descarca o singura data. Fara internet merge pe ce e deja in cache.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests

API = 'https://api.deadlock-api.com'
UA = {'User-Agent': 'deadlock-helper/0.1 (local overlay)'}
DAY = 24 * 3600


def http_json(url, params=None, timeout=30):
    r = requests.get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


class Assets:
    def __init__(self, home):
        self.dir = os.path.join(home, 'cache')
        self.img = os.path.join(self.dir, 'img')
        os.makedirs(self.img, exist_ok=True)
        self.heroes = {}      # id -> {id, name, card, icon}
        self.items = {}       # id -> {id, name, slot, tier, cost, icon, active}

    # --- liste ---------------------------------------------------------------

    def _cached(self, name, url, max_age=DAY):
        path = os.path.join(self.dir, name)
        fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age
        if not fresh:
            try:
                data = http_json(url, timeout=60)
                tmp = path + '.part'
                with open(tmp, 'w', encoding='utf8') as f:
                    json.dump(data, f)
                os.replace(tmp, path)
                return data
            except Exception:
                if not os.path.exists(path):
                    raise
        with open(path, encoding='utf8') as f:
            return json.load(f)

    def load(self):
        heroes = self._cached('heroes.json', f'{API}/v1/assets/heroes?only_active=true')
        for h in heroes:
            if not h.get('player_selectable') or h.get('disabled'):
                continue
            img = h.get('images') or {}
            if not img.get('icon_hero_card'):
                continue
            self.heroes[h['id']] = {
                'id': h['id'], 'name': h['name'],
                'card_url': img['icon_hero_card'],
                'icon_url': img.get('icon_image_small') or img['icon_hero_card'],
            }
        items = self._cached('items.json', f'{API}/v1/assets/items')
        by_class_all = {it.get('class_name'): it for it in items}
        # cele 4 abilitati ale fiecarui erou: dupa ele aflam din HUD ce erou esti
        for h in heroes:
            if h['id'] not in self.heroes:
                continue
            abil = []
            for k in ('signature1', 'signature2', 'signature3', 'signature4'):
                a = by_class_all.get((h.get('items') or {}).get(k))
                if a and a.get('image'):
                    abil.append({'id': a['id'], 'name': a['name'], 'image_url': a['image']})
            self.heroes[h['id']]['abilities'] = abil
        self.ability_names = {a['id']: a['name'] for a in items if a.get('type') == 'ability'}
        for it in items:
            if it.get('type') != 'upgrade' or not it.get('shopable') or it.get('disabled'):
                continue
            if (it.get('item_tier') or 0) > 4:     # tier 5: nu se cumpara din magazin normal
                continue
            self.items[it['id']] = {
                'id': it['id'], 'name': it['name'], 'slot': it.get('item_slot_type'),
                'tier': it.get('item_tier'), 'cost': it.get('cost'),
                'active': bool(it.get('is_active_item')),
                'imbue': bool(it.get('imbue')),
                'icon_url': it.get('shop_image') or it.get('image'),
                'upgrades_from': [],
            }
        # itemele care se construiesc din altele (component -> upgrade)
        by_class = {it.get('class_name'): it['id'] for it in items if it.get('type') == 'upgrade'}
        for it in items:
            if it['id'] in self.items:
                for comp in it.get('component_items') or []:
                    cid = by_class.get(comp)
                    if cid:
                        self.items[it['id']]['upgrades_from'].append(cid)
        return self

    # --- imagini -------------------------------------------------------------

    def image_path(self, kind, key):
        return os.path.join(self.img, f'{kind}_{key}.png')

    def _download(self, url, path):
        if os.path.exists(path) or not url:
            return path if os.path.exists(path) else None
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            tmp = path + '.part'
            with open(tmp, 'wb') as f:
                f.write(r.content)
            os.replace(tmp, path)
            return path
        except Exception:
            return None

    def fetch_images(self):
        jobs = []
        for h in self.heroes.values():
            jobs.append((h['card_url'], self.image_path('card', h['id'])))
            jobs.append((h['icon_url'], self.image_path('hero', h['id'])))
            for a in h.get('abilities', []):
                jobs.append((a['image_url'], self.image_path('abil', a['id'])))
        for it in self.items.values():
            jobs.append((it['icon_url'], self.image_path('item', it['id'])))
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda j: self._download(*j), jobs))
        missing = [h['name'] for h in self.heroes.values()
                   if not os.path.exists(self.image_path('card', h['id']))]
        return missing
