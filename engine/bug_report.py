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
    lines = [f"versiune: {version}",
             f"windows: {platform.platform()}",
             f"frozen: {getattr(sys, 'frozen', False)}"]
    if engine is not None:
        try:
            g = engine.game or {}
            lines.append(f"stare: {engine.view}, joc: {'da' if g else 'nu'}, fereastra: {g.get('rect')}, "
                         f"scala HUD: {engine.topbar.scale if engine.topbar else '-'}")
            names = {h: v['name'] for h, v in engine.assets.heroes.items()}
            heroes = [names.get(h, '-') for h in engine.tracker.heroes()]
            lines.append(f"eroi: {', '.join(heroes)}; slotul tau: {engine.tracker.own_slot()}")
            lines.append(f"corectate de mana: {sorted(engine.tracker.manual)}; rang: {engine.stats.badge}")
            if engine.rec_error:
                lines.append(f"statistici: {engine.rec_error}")
        except Exception as e:
            lines.append(f"(diagnostic incomplet: {type(e).__name__})")
    for name in ("eroare.log", "engine.log"):
        try:
            with open(os.path.join(home, name), encoding="utf-8") as f:
                lines.append(f"{name} (final):\n" + f.read()[-800:])
        except OSError:
            pass
    return "\n".join(lines)


def validate(description, email):
    """Mesaj de eroare pentru utilizator, sau None daca e ok."""
    if len(description.strip()) < 10:
        return "Descrie problema in cateva cuvinte (minim 10 caractere)."
    if len(description) > MAX_TEXT:
        return f"Prea lung (maxim {MAX_TEXT} caractere)."
    email = email.strip()
    if email and not ("@" in email and "." in email.split("@")[-1] and " " not in email):
        return "Adresa de email nu pare valida (las-o goala daca nu vrei raspuns)."
    return None


def send(description, email, diagnostics, version, timeout=10):
    """Trimite raportul. Intoarce (ok, mesaj). Nu ridica niciodata exceptii."""
    global _last_sent
    wait = COOLDOWN - (time.monotonic() - _last_sent)
    if _last_sent and wait > 0:
        return False, f"Asteapta {int(wait)}s inainte de un nou raport."
    payload = {
        "_subject": f"[Deadlock Helper {version}] bug report",
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
            return True, "Trimis. Multumim!"
        msg = data.get("message") or ""
        if "Activation" in msg:
            return False, "Raportarea nu e activata inca pe server. Foloseste DESCHIDE EMAIL."
        return False, msg or f"Serverul a raspuns {r.status_code}."
    except Exception as e:
        return False, f"Nu am putut trimite ({type(e).__name__})."


def mailto(description, diagnostics, version):
    """Rezerva: un mailto: precompletat (limitat ca lungime de Windows)."""
    q = urllib.parse.urlencode(
        {"subject": f"[Deadlock Helper {version}] bug report",
         "body": description.strip()[:900] + "\n\n--\n" + diagnostics[:600]},
        quote_via=urllib.parse.quote)
    webbrowser.open(f"mailto:{TO}?{q}")
