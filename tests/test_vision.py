"""Ruleaza recunoasterea pe cadrele din tests/frames si compara cu adevarul stiut.
Cadrele nu sunt in repo (capturi din clipuri); fara ele testul se sare."""
import glob, os, sys, time
import cv2
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from engine.assets import Assets
from engine.vision import TopBar, Tracker, load_templates

TRUTH = {
    'yt_rem_904': ['Wraith', 'Seven', 'Billy', 'Rem', 'Rat King', 'Deadman Danny',
                   'Mirage', 'Ivy', 'Apollo', 'Abrams', 'Haze', 'Grey Talon'],
}
TRUTH['yt_rem_1500'] = TRUTH['yt_rem_904']


def main(home):
    a = Assets(home).load()
    a.fetch_images()
    t0 = time.time(); tb = TopBar(load_templates(a)); print(f'sabloane {time.time()-t0:.1f}s')
    names = {h: v['name'] for h, v in a.heroes.items()}
    ok = total = 0
    for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), 'frames', '*.png'))):
        key = os.path.basename(path)[:-4]
        f = cv2.imread(path)
        band, cx = TopBar.strip(f, f.shape[1] / 2)
        t0 = time.time(); slots = tb.read(band, cx); dt = time.time() - t0
        tr = Tracker()
        for _ in range(3): tr.update(slots)
        got = [names.get(h, '?') for h in tr.heroes()]
        truth = TRUTH.get(key)
        print(f'{key}: {dt*1000:.0f} ms, scala {tb.scale}')
        for i, s in enumerate(slots):
            exp = truth[i] if truth else '?'
            top = ' | '.join(f'{names[h]} {v:.2f}' for v, h in s['scores'][:2]) if s else '-'
            mark = 'OK ' if got[i] == exp else '-- '
            print(f'  {mark}{i:2d} {exp:14s} -> {got[i]:14s} [{top}]')
            ok += got[i] == exp; total += 1
    print(f'corect {ok}/{total}')
    # invatare: corectam Deadman Danny pe un cadru, apoi trebuie gasit singur pe celalalt
    import tempfile
    danny = next(h for h, v in a.heroes.items() if v['name'] == 'Deadman Danny')
    with tempfile.TemporaryDirectory() as d:
        tpl = load_templates(a, d)
        tb2 = TopBar(tpl)
        f = cv2.imread(os.path.join(os.path.dirname(__file__), 'frames', 'yt_rem_904.png'))
        if f is None:
            return
        band, cx = TopBar.strip(f, f.shape[1] / 2)
        slots = tb2.read(band, cx)
        tpl.learn(danny, band, slots[5]['x'], tb2.scale)
        reread = load_templates(a, d)            # si din fisier, ca dupa o repornire
        tb3 = TopBar(reread)
        f2 = cv2.imread(os.path.join(os.path.dirname(__file__), 'frames', 'yt_rem_1500.png'))
        for name, frame in (('acelasi cadru', f), ('alt cadru', f2)):
            b, c = TopBar.strip(frame, frame.shape[1] / 2)
            top = tb3.read(b, c)[5]['scores'][:2]
            print(f'invatat Danny, {name}: ' + ' | '.join(f'{names[h]} {v:.2f}' for v, h in top))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'scratch', 'home'))
