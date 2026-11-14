'use strict'
// Textele interfetei, in romana si engleza. Limba vine din Windows, iar butonul
// din bara panoului o schimba (se tine minte).

const STRINGS = {
  ro: {
    status_loading: 'pornesc', status_idle: 'astept meciul', status_closed: 'jocul e inchis',
    status_searching: 'caut eroii', status_match: 'in meci', status_manual: 'manual', status_error: 'eroare',
    update: 'Update {v}', update_hint: 'Reporneste pe versiunea noua', checking: 'verific...',
    up_to_date: 'esti la zi', update_error: 'eroare: {e}',
    collapse_hint: 'Strange panoul (CTRL+ALT+D)', close_hint: 'Inchide', report_hint: 'Raporteaza o problema',
    lang_hint: 'Limba: romana. Click pentru engleza.',
    loading: 'Incarc eroii si itemele...',
    teams: 'Echipe', reading_top: 'citesc bara de sus', your_wr: 'win rate-ul tau contra lor',
    left: 'Stanga', right: 'Dreapta', your_team: 'Echipa ta', enemies: 'Inamici', you: 'tu',
    slot_hint: '{name}. Click ca sa corectezi.', slot_you_hint: '{name} (tu). Click ca sa corectezi.',
    slot_unknown: 'Nu l-am recunoscut inca. Click ca sa-l alegi.',
    who_are_you: 'Nu stiu inca care esti tu. <b>Apasa pe portretul tau</b> si alege "Eu sunt aici".',
    manual_title: 'Alege de mana', manual_note: 'pana porneste meciul', manual_you: 'Tu',
    pick_your_hero: 'Alege eroul tau', pick_enemy: 'Alege un inamic', change_hint: '{name}. Click ca sa schimbi.',
    manual_help: 'In meci gasesc singur eroii din bara de sus. Pana atunci ii poti alege aici.',
    computing: 'Calculez build-ul contra lor...', updating: 'Actualizez build-ul...', waiting_data: 'Astept datele...',
    stats_down: 'Statisticile nu raspund acum, reincerc.',
    details: 'Detalii', less: 'Mai putin',
    buy_now: 'Cumpara acum', from_owned: 'din ce ai deja', have: 'Ai',
    imbue_on: 'imbue pe {a}', of_builds: '{p}% din build-uri',
    why_vs: 'contra {names}', why_from: 'se face din {names}', why_pick: 'luat in {p}% din meciuri, {wr}% win rate',
    counters: 'Contra lor', counters_note: 'fata de cum merge de obicei', vs: 'vs {names}', weak_vs: 'slab vs {name}',
    good_vs_them: 'bun contra lor', weaker_vs_them: 'mai slab contra lor',
    build: 'Build {hero}', winrate: 'win rate',
    weaker_now: 'Mai slabe acum', weaker_note: 'populare, dar nu contra lor',
    footer: '{k}k meciuri din {d}', rank_hint: 'Doar meciurile de la rangul asta in sus', all_ranks: 'Toate rangurile',
    who_in_slot: 'Cine e in slotul asta?', your_hero: 'Eroul tau', enemy: 'Inamic', im_here: 'Eu sunt aici', clear: 'Sterge',
    tip_wr: 'Win rate <b>{wr}%</b> in {n} meciuri, luat in <b>{p}%</b> din ele',
    tip_buy: 'Cumparat de obicei pe la minutul <b>{m}</b>', tip_imbue: 'Imbue: <b>{list}</b> din build-urile populare',
    tip_vs: 'Contra {name}:',
    report_title: 'Raporteaza o problema', report_what: 'Ce s-a intamplat?',
    report_placeholder: 'De exemplu: a recunoscut Haze in loc de Wraith in slotul 3',
    report_email: 'Email, daca vrei raspuns (optional)', report_include: 'Include diagnosticul de mai jos',
    report_send: 'Trimite', report_sending: 'Se trimite...', report_mail: 'Deschide emailul',
    report_no_engine: 'Motorul nu a raspuns. Incearca din nou.', report_close_hint: 'Inchide (Esc)',
  },
  en: {
    status_loading: 'starting', status_idle: 'waiting for a match', status_closed: 'game is closed',
    status_searching: 'finding heroes', status_match: 'in match', status_manual: 'manual', status_error: 'error',
    update: 'Update {v}', update_hint: 'Restart on the new version', checking: 'checking...',
    up_to_date: 'up to date', update_error: 'error: {e}',
    collapse_hint: 'Collapse the panel (CTRL+ALT+D)', close_hint: 'Close', report_hint: 'Report a problem',
    lang_hint: 'Language: English. Click for Romanian.',
    loading: 'Loading heroes and items...',
    teams: 'Teams', reading_top: 'reading the top bar', your_wr: 'your win rate against them',
    left: 'Left', right: 'Right', your_team: 'Your team', enemies: 'Enemies', you: 'you',
    slot_hint: '{name}. Click to correct.', slot_you_hint: '{name} (you). Click to correct.',
    slot_unknown: 'Not recognized yet. Click to pick.',
    who_are_you: 'I do not know which one is you yet. <b>Click your portrait</b> and choose "This is me".',
    manual_title: 'Pick by hand', manual_note: 'until the match starts', manual_you: 'You',
    pick_your_hero: 'Pick your hero', pick_enemy: 'Pick an enemy', change_hint: '{name}. Click to change.',
    manual_help: 'In a match I find the heroes from the top bar myself. Until then you can pick them here.',
    computing: 'Working out the build against them...', updating: 'Updating the build...', waiting_data: 'Waiting for data...',
    stats_down: 'The stats are not responding right now, retrying.',
    details: 'Details', less: 'Less',
    buy_now: 'Buy now', from_owned: 'based on what you have', have: 'You have',
    imbue_on: 'imbue on {a}', of_builds: '{p}% of builds',
    why_vs: 'against {names}', why_from: 'builds from {names}', why_pick: 'bought in {p}% of matches, {wr}% win rate',
    counters: 'Against them', counters_note: 'compared to how it usually does', vs: 'vs {names}', weak_vs: 'weak vs {name}',
    good_vs_them: 'good against them', weaker_vs_them: 'weaker against them',
    build: '{hero} build', winrate: 'win rate',
    weaker_now: 'Weaker right now', weaker_note: 'popular, but not against them',
    footer: '{k}k matches since {d}', rank_hint: 'Only matches from this rank up', all_ranks: 'All ranks',
    who_in_slot: 'Who is in this slot?', your_hero: 'Your hero', enemy: 'Enemy', im_here: 'This is me', clear: 'Clear',
    tip_wr: 'Win rate <b>{wr}%</b> in {n} matches, bought in <b>{p}%</b> of them',
    tip_buy: 'Usually bought around minute <b>{m}</b>', tip_imbue: 'Imbue: <b>{list}</b> in popular builds',
    tip_vs: 'Against {name}:',
    report_title: 'Report a problem', report_what: 'What happened?',
    report_placeholder: 'For example: it recognized Haze instead of Wraith in slot 3',
    report_email: 'Email, if you want a reply (optional)', report_include: 'Include the diagnostics below',
    report_send: 'Send', report_sending: 'Sending...', report_mail: 'Open email',
    report_no_engine: 'The engine did not answer. Try again.', report_close_hint: 'Close (Esc)',
  },
}

let LANG = 'en'

function setLang(l) { LANG = STRINGS[l] ? l : 'en' }

// t('why_vs', { names: 'Haze' }); valorile din {} se pun asa cum sunt (escapate de apelant)
function t(key, vars) {
  const s = STRINGS[LANG][key] ?? STRINGS.en[key] ?? key
  return vars ? s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '') : s
}
