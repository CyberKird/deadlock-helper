# Deadlock Helper

Un overlay local pentru Deadlock. Recunoaște eroii din bara de sus a HUD-ului, află care ești tu și îți arată cele mai bune iteme pentru eroul tău, contra echipei adverse. Datele vin din patch-ul curent.

## Ce face

- **Recunoaște toți cei 12 eroi** din bara de sus, din captura ecranului. Nu atinge jocul: nimic injectat, nimic citit din memoria lui.
- **Află care ești tu** după fundalul evidențiat al slotului tău. Dacă nu reușește, apeși pe portretul tău și alegi „Eu sunt aici”.
- **Itemele contra lor**: itemele care merg mai bine decât de obicei pe eroul tău când în echipa adversă sunt eroii ăștia, plus pe cine contrează fiecare.
- **Build pe etape** (800 / 1600 / 3200 / 6400): cele mai bune iteme din fiecare tier, cu semn când un item e bun sau mai slab contra compoziției lor.
- **Win rate-ul tău contra fiecărui inamic**, sub portretul lui.
- **Mai slabe acum**: iteme populare care merg mai prost contra echipei lor.
- **Corectezi cu un click**: apeși pe orice portret și alegi alt erou. Fără meci, alegi de mână eroul tău și inamicii.
- **Filtru de rang**: doar meciurile de la un anumit rang în sus.

## Cum funcționează

**Recunoașterea.** Din fișierele de UI ale jocului (`citadel_hud_top_bar.vcss`, `hero_badge.vcss`) se vede exact cum e desenată bara: în fiecare slot e imaginea „card” a eroului (280x380), scalată la 70.4 px lățime la 1080p, tăiată cu o mască în formă de U. Motorul face același lucru cu card-urile luate din API, apoi le caută pe fiecare slot prin potrivire de șablon (`TM_CCOEFF_NORMED` cu mască). Întâi la jumătate de rezoluție pe toți eroii, apoi la rezoluție plină pe primii candidați. Un erou mort e desaturat, așa că se compară și în gri. Rezultatele se votează pe mai multe cadre, deci un cadru prost nu schimbă nimic.

**Statisticile.** Vin de pe [deadlock-api.com](https://deadlock-api.com), pe ultimele 14 zile, dar nu de dinainte de ultimul patch mare. Pentru fiecare inamic se compară win rate-ul unui item în meciurile cu el cu win rate-ul obișnuit al itemului. Win rate-ul brut al itemelor scumpe e umflat (le cumpără cine deja câștigă), de aceea itemele se compară doar în același tier. Iar când sunt puține meciuri, rezultatul e tras spre medie, ca un item rar să nu pară minune.

Aplicația are două bucăți: **motorul** (Python, `app.py` + `engine/`) și **interfața** (Electron, `ui/`). Interfața pornește motorul ca proces copil și vorbesc prin JSON pe stdin/stdout. Datele și imaginile stau în `%APPDATA%\deadlock-helper`.

## Instalare

**Din exe:** rulezi `Deadlock-Helper.exe`. Se instalează singur (fără întrebări, fără drepturi de admin), pune o scurtătură pe desktop și pornește. Windows SmartScreen poate avertiza la prima rulare, pentru că exe-ul nu e semnat: `More info`, apoi `Run anyway`. Update-urile se descarcă singure în fundal și se instalează când închizi aplicația. Cât jocul e închis, aplicația repornește singură pe versiunea nouă.

**Din sursă:** `INSTALL.bat` (cere Python 3.11+ și Node.js), apoi `START.bat`.

`CTRL+ALT+D` strânge sau deschide panoul. Panoul se mută trăgând de bara lui și rămâne unde l-ai lăsat. Jocul trebuie să fie în modul borderless (fereastră fără margini), ca panoul să stea deasupra lui. Butonul `!` din bara panoului trimite un raport de problemă la contact@joltarise.com. Înainte să-l trimiți, vezi exact ce pleacă.

## Build

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\pyinstaller engine.spec --noconfirm --clean      # -> dist\dlh-engine\
dist\dlh-engine\dlh-engine.exe --selfcheck
cd ui && npx electron-builder --win nsis --publish never        # -> dist\Deadlock-Helper.exe
```

Versiunea e una singură, în `ui/package.json`: o ridici înainte de build, egală cu tag-ul Release-ului. În Release pui trei fișiere din `dist\`: `Deadlock-Helper.exe`, `Deadlock-Helper.exe.blockmap` și `latest.yml`.

## Verificare

```bash
.venv\Scripts\python app.py --selfcheck
```

Cu cadre de test în `tests/frames` (capturi ale jocului, nu sunt în repo), rulează și recunoașterea pe ele.
