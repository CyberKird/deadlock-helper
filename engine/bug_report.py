"""Raport de bug trimis la contact@joltarise.com, direct din aplicatie.

Transport: FormSubmit (formsubmit.co) -- un POST JSON, fara server propriu si
fara credentiale de email in exe. La primul raport, FormSubmit trimite un mail
de activare la contact@joltarise.com; pana e confirmat o data, raportul nu
ajunge. Daca trimiterea pica (fara internet, endpoint blocat), dialogul ofera
un mailto: precompletat ca rezerva.

Ce pleaca: descrierea scrisa de utilizator, emailul lui (optional) si, doar daca
lasa bifat, un bloc de diagnostic pe care il vede inainte sa trimita (versiune,
Windows, starea, eroii cititi, ultima eroare). Nicio captura de ecran.
"""

import os
import platform
import sys
import time
import urllib.parse
import webbrowser

import requests

TO = "contact@joltarise.com"
ENDPOINT = f"https://formsubmit.co/ajax/{TO}"
# FormSubmit respinge cererile fara Origin/Referer ("open this page through a
# web server"): un POST din Python nu le trimite singur.
ORIGIN = "https://joltarise.com"
MAX_TEXT = 2000
COOLDOWN = 60          # secunde intre doua trimiteri, impotriva apasarilor repetate
_last_sent = 0.0


def build_diagnostics(version, home, engine=None):
    """Blocul de diagnostic, ca text. Orice sursa lipsa e sarita, nu crapa."""
    lines = [f"version: {version}",
             f"windows: {platform.platform()}",
             f"frozen: {getattr(sys, 'frozen', False)}"]
    if engine is not None:
        try:
            g = engine.game or {}
            lines.append(f"view: {engine.view}, game: {'yes' if g else 'no'}, window: {g.get('rect')}, "
                         f"HUD scale: {engine.topbar.scale if engine.topbar else '-'}, lang: {engine.lang}")
            names = {h: v['name'] for h, v in engine.assets.heroes.items()}
            heroes = [names.get(h, '-') for h in engine.tracker.heroes()]
            lines.append(f"heroes: {', '.join(heroes)}; your slot: {engine.tracker.own_slot()}; your hero: {engine.own_hero}")
            lines.append(f"corrected by hand: {sorted(engine.tracker.manual)}; rank: {engine.stats.badge}; items: {sorted(engine.owned.values())}")
            if engine.rec_error:
                lines.append(f"stats: {engine.rec_error}")
        except Exception as e:
            lines.append(f"(diagnostics incomplete: {type(e).__name__})")
    for name in ("eroare.log", "engine.log"):
        try:
            with open(os.path.join(home, name), encoding="utf-8") as f:
                lines.append(f"{name} (final):\n" + f.read()[-800:])
        except OSError:
            pass
    return "\n".join(lines)


TEXT = {
    "ro": {
        "short": "Descrie problema in cateva cuvinte (minim 10 caractere).",
        "long": "Prea lung (maxim {n} caractere).",
        "email": "Adresa de email nu pare valida (las-o goala daca nu vrei raspuns).",
        "wait": "Asteapta {n}s inainte de un nou raport.",
        "sent": "Trimis. Multumim!",
        "inactive": "Raportarea nu e activata inca pe server. Foloseste Deschide emailul.",
        "status": "Serverul a raspuns {n}.",
        "failed": "Nu am putut trimite ({n}).",
    },
    "en": {
        "short": "Describe the problem in a few words (at least 10 characters).",
        "long": "Too long (at most {n} characters).",
        "email": "That email address does not look valid (leave it empty if you do not want a reply).",
        "wait": "Wait {n}s before sending another report.",
        "sent": "Sent. Thank you!",
        "inactive": "Reporting is not activated on the server yet. Use Open email.",
        "status": "The server answered {n}.",
        "failed": "Could not send ({n}).",
    },
}


def _t(lang, key, n=""):
    return TEXT.get(lang, TEXT["en"])[key].format(n=n)


def validate(description, email, lang="en"):
    """Mesaj de eroare pentru utilizator, sau None daca e ok."""
    if len(description.strip()) < 10:
        return _t(lang, "short")
    if len(description) > MAX_TEXT:
        return _t(lang, "long", MAX_TEXT)
    email = email.strip()
    if email and not ("@" in email and "." in email.split("@")[-1] and " " not in email):
        return _t(lang, "email")
    return None


def send(description, email, diagnostics, version, timeout=10, lang="en"):
    """Trimite raportul. Intoarce (ok, mesaj). Nu ridica niciodata exceptii."""
    global _last_sent
    wait = COOLDOWN - (time.monotonic() - _last_sent)
    if _last_sent and wait > 0:
        return False, _t(lang, "wait", int(wait))
    payload = {
        "_subject": f"[Soulsight {version}] bug report",
        "_template": "box",
        "_captcha": "false",
        "_honey": "",
        "message": description.strip()[:MAX_TEXT],
        "diagnostic": diagnostics[:6000],
    }
    if email.strip():
        payload["email"] = email.strip()      # FormSubmit il foloseste ca Reply-To
    try:
        r = requests.post(ENDPOINT, json=payload, timeout=timeout,
                          headers={"Accept": "application/json", "Origin": ORIGIN,
                                   "Referer": ORIGIN + "/"})
        data = r.json() if r.content else {}
        if r.status_code == 200 and str(data.get("success")).lower() == "true":
            _last_sent = time.monotonic()
            return True, _t(lang, "sent")
        msg = data.get("message") or ""
        if "Activation" in msg:
            return False, _t(lang, "inactive")
        return False, msg or _t(lang, "status", r.status_code)
    except Exception as e:
        return False, _t(lang, "failed", type(e).__name__)


def mailto(description, diagnostics, version):
    """Rezerva: un mailto: precompletat (limitat ca lungime de Windows)."""
    q = urllib.parse.urlencode(
        {"subject": f"[Soulsight {version}] bug report",
         "body": description.strip()[:900] + "\n\n--\n" + diagnostics[:600]},
        quote_via=urllib.parse.quote)
    webbrowser.open(f"mailto:{TO}?{q}")
