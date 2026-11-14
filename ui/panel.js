'use strict'
// Panoul: deseneaza starea primita de la motor si trimite corecturile tale.
// Textele sunt in i18n.js (t()).

const $ = s => document.querySelector(s)
const body = $('#body'), picker = $('#picker'), tip = $('#tip')
let S = null                       // ultima stare
let draft = { hero: null, enemies: [null, null, null, null, null, null] }   // modul manual
let pick = null                    // ce slot alegi acum
let details = false                // in meci: panoul intreg in loc de cel compact
const items = {}                   // id -> item, pentru tooltip

const img = (kind, id) => `dlh://img/${kind}_${id}.png`
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const sign = v => (v > 0 ? '+' : '') + v.toFixed(1)
const heroName = id => S?.heroes.find(h => h.id === id)?.name || '?'
const names = list => list.map(esc).join(', ')

const RANKS = [[null, 'all_ranks'], [50, 'Ritualist+'], [60, 'Emissary+'], [70, 'Archon+'],
  [80, 'Oracle+'], [90, 'Phantom+'], [100, 'Ascendant+']]

window.dlh.onState(s => {
  S = s
  setLang(s.lang)
  document.documentElement.lang = s.lang
  document.body.classList.toggle('collapsed', !!s.collapsed)
  if (s.state?.manual && !draft.hero) {
    draft = { hero: s.state.manual.hero, enemies: [...s.state.manual.enemies, null, null, null, null, null, null].slice(0, 6) }
  }
  render()
})

$('#btn-close').onclick = () => window.dlh.cmd({ cmd: 'close' })
$('#btn-collapse').onclick = () => window.dlh.cmd({ cmd: 'collapse' })
$('#btn-report').onclick = () => window.dlh.cmd({ cmd: 'report' })
$('#btn-update').onclick = () => window.dlh.cmd({ cmd: 'update' })
$('#btn-lang').onclick = () => window.dlh.cmd({ cmd: 'lang', value: S?.lang === 'ro' ? 'en' : 'ro' })

// --- desen ---------------------------------------------------------------------------

function header(st, view) {
  const status = $('#status')
  status.className = 'pill' + (view === 'match' ? ' live' : '')
  status.textContent = S.error ? t('status_error')
    : view === 'idle' ? t(st.game?.running ? 'status_idle' : 'status_closed')
      : t('status_' + view)
  const up = $('#btn-update'), u = S.update || {}
  up.hidden = !(u.tag || u.busy || u.why)
  up.className = 'text-btn' + (u.tag ? '' : ' quiet')
  up.textContent = u.tag ? t('update', { v: u.tag }) : u.busy ? t('checking')
    : u.why === 'latest' ? t('up_to_date') : u.why ? t('update_error', { e: u.why }) : ''
  up.dataset.hint = u.tag ? t('update_hint') : ''
  const lang = $('#btn-lang')
  lang.textContent = (S.lang || 'en').toUpperCase()
  lang.dataset.hint = t('lang_hint')
  $('#btn-report').dataset.hint = t('report_hint')
  $('#btn-collapse').dataset.hint = t('collapse_hint')
  $('#btn-close').dataset.hint = t('close_hint')
}

function render() {
  const st = S.state || {}
  const view = st.view || 'loading'
  header(st, view)
  let html = ''
  if (S.error) html += `<section><div class="hint error">${esc(S.error)}</div></section>`
  if (view === 'match' && st.own != null && !details) {
    // in meci, cu tot ce trebuie aflat: doar ce cumperi acum. Restul la "Detalii".
    html += compact(st)
  } else {
    if (view === 'match' || view === 'searching') html += teamsLive(st)
    else if (view !== 'loading') html += teamsManual()
    if (view === 'loading') html += `<section><div class="hint">${t('loading')}</div></section>`
    html += recommendation(st)
  }
  body.innerHTML = html
  bind()
  measure()
}

function why(it) {
  return (it.why || []).map(w => w.k === 'vs' ? t('why_vs', { names: names(w.names) })
    : w.k === 'from' ? t('why_from', { names: names(w.names) })
      : t('why_pick', { p: w.pick.toFixed(0), wr: w.wr.toFixed(1) })).join('; ')
}

const imbueText = imb => imb?.length ? t('imbue_on', { a: esc(imb[0].name) }) : ''
const icon = (it, cls = '') => `<span class="ico ${it.slot} ${cls}" style="background-image:url(${img('item', it.id)})"></span>`

function teamsLive(st) {
  const own = st.own
  const slots = st.slots || []
  const wr = {}
  for (const m of st.rec?.matchups || []) wr[m.hero] = m.wr
  const row = (from, label) => {
    let h = `<div class="team"><span class="label">${label}</span>`
    for (const s of slots.slice(from, from + 6)) {
      const cls = ['slot', s.side || '', s.you ? 'you' : '', s.manual ? 'manual' : '', s.hero ? '' : 'empty'].join(' ')
      let sub = `<span class="sub">${s.you ? t('you') : ''}</span>`
      if (s.side === 'enemy' && wr[s.hero] != null) {
        const v = wr[s.hero]
        sub = `<span class="sub ${v >= 52 ? 'good' : v <= 48 ? 'bad' : ''}">${v.toFixed(0)}%</span>`
      }
      const face = s.hero ? `<span class="face" style="background-image:url(${img('hero', s.hero)})"></span>`
        : '<span class="face">?</span>'
      const hint = !s.hero ? t('slot_unknown') : t(s.you ? 'slot_you_hint' : 'slot_hint', { name: s.name })
      h += `<button class="${cls}" data-slot="${s.slot}" data-hint="${esc(hint)}">${face}${sub}</button>`
    }
    return h + '</div>'
  }
  const left = own == null ? t('left') : own < 6 ? t('your_team') : t('enemies')
  const right = own == null ? t('right') : own < 6 ? t('enemies') : t('your_team')
  let h = `<section><h2>${t('teams')} <span class="note">${st.view === 'searching' ? t('reading_top') : t('your_wr')}</span></h2>`
  h += row(0, left) + row(6, right)
  if (own == null && slots.some(s => s.hero)) h += `<div class="hint">${t('who_are_you')}</div>`
  return h + '</section>'
}

function teamsManual() {
  const slot = (key, id, label) => {
    const face = id ? `<span class="face" style="background-image:url(${img('hero', id)})"></span>` : '<span class="face">+</span>'
    return `<button class="slot ${id ? '' : 'empty'} ${key === 'hero' ? 'you' : 'enemy'}" data-manual="${key}"
      data-hint="${esc(id ? t('change_hint', { name: heroName(id) }) : label)}">${face}<span class="sub"></span></button>`
  }
  let h = `<section><h2>${t('manual_title')} <span class="note">${t('manual_note')}</span></h2>`
  h += `<div class="team"><span class="label">${t('manual_you')}</span>${slot('hero', draft.hero, t('pick_your_hero'))}</div>`
  h += `<div class="team"><span class="label">${t('enemies')}</span>`
  draft.enemies.forEach((e, i) => { h += slot('e' + i, e, t('pick_enemy')) })
  h += '</div>'
  if (!draft.hero) h += `<div class="hint">${t('manual_help')}</div>`
  return h + '</section>'
}

// Modul compact din meci: itemul de cumparat, doua variante ca iconite,
// imbue-urile itemelor tale. Explicatiile sunt la hover.
function compact(st) {
  const rec = st.rec
  if (!rec) {
    const msg = st.busy ? t('computing') : st.error ? t('stats_down') : t('waiting_data')
    return `<section><div class="hint">${msg}</div>${detailsBtn()}</section>`
  }
  remember(rec, st)
  const next = st.next || []
  let h = '<section class="now">'
  if (next.length) {
    const it = next[0]
    h += `<div class="big" data-item="${it.id}">${icon(it)}
      <span class="txt"><span class="name">${esc(it.name)}</span>
        ${it.imbue ? `<span class="imbue">${imbueText(it.imbue)}</span>` : `<span class="why">${why(it)}</span>`}</span>
      <span class="cost">${it.cost}</span>`
    if (next.length > 1) {
      h += '<span class="alts">'
      for (const alt of next.slice(1, 3)) h += icon(alt).replace('<span ', `<span data-item="${alt.id}" `)
      h += '</span>'
    }
    h += '</div>'
  }
  const imb = (st.owned || []).filter(o => o.imbue)
  if (imb.length) {
    h += '<div class="chips imbues"><span class="label">Imbue</span>'
    for (const o of imb) {
      const hint = `${o.name}: ${imbueText(o.imbue)} (${t('of_builds', { p: o.imbue[0].share })})`
      h += `<span class="chip" data-hint="${esc(hint)}">${icon(o)}${esc(o.imbue[0].name)}</span>`
    }
    h += '</div>'
  }
  return h + detailsBtn() + '</section>'
}

function detailsBtn() {
  return `<button class="more" id="btn-details">${details ? t('less') : t('details')}</button>`
}

function remember(rec, st) {
  for (const k in items) delete items[k]
  const all = [...(rec.pool || []), ...rec.counter_picks, ...rec.avoid, ...rec.tiers.flatMap(x => x.items), ...(st.next || [])]
  for (const it of all) items[it.id] = { ...items[it.id], ...it }
}

// Panoul intreg: ce cumperi acum (cu explicatii), ce ai, contra lor, build-ul.
function buyNow(st) {
  const next = st.next || []
  const owned = st.owned || []
  if (!next.length && !owned.length) return ''
  let h = `<section class="now"><h2>${t('buy_now')} <span class="note">${t('from_owned')}</span></h2>`
  if (next.length) {
    const it = next[0]
    h += `<div class="big" data-item="${it.id}">${icon(it)}
      <span class="txt"><span class="name">${esc(it.name)}</span><span class="why">${why(it)}</span>
        ${it.imbue ? `<span class="imbue">${imbueText(it.imbue)} (${t('of_builds', { p: it.imbue[0].share })})</span>` : ''}</span>
      <span class="cost">${it.cost}</span></div>`
    for (const alt of next.slice(1, 3)) {
      h += `<div class="row" data-item="${alt.id}">${icon(alt)}
        <span class="name">${esc(alt.name)}<span class="why">${why(alt)}</span></span><span class="num">${alt.cost}</span></div>`
    }
  }
  if (owned.length) {
    h += `<div class="owned"><span class="label">${t('have')}</span><div class="chips">`
    for (const o of owned) {
      const hint = o.imbue ? `${o.name}: ${imbueText(o.imbue)} (${t('of_builds', { p: o.imbue[0].share })})` : o.name
      h += `<span class="chip ${o.slot}" data-hint="${esc(hint)}">${icon(o)}${o.imbue ? `<span class="imb">${esc(o.imbue[0].name)}</span>` : ''}</span>`
    }
    h += '</div></div>'
  }
  return h + '</section>'
}

function itemRow(it, mode) {
  let w = '', num = ''
  if (mode === 'counter') {
    w = it.vs_good.length ? t('vs', { names: names(it.vs_good.map(v => v.name)) }) : ''
    num = `<span class="num good">${sign(it.counter)}%</span>`
  } else if (mode === 'avoid') {
    w = it.vs_bad.length ? t('weak_vs', { name: esc(it.vs_bad[0].name) }) : ''
    num = `<span class="num bad">${sign(it.counter)}%</span>`
  } else {
    if (it.counter >= 1) w = t('good_vs_them')
    else if (it.counter <= -1) w = t('weaker_vs_them')
    num = `<span class="num">${it.wr.toFixed(1)}%</span>`
  }
  return `<div class="row" data-item="${it.id}">${icon(it)}
    <span class="name">${esc(it.name)}${w ? `<span class="why">${w}</span>` : ''}</span>${num}</div>`
}

function recommendation(st) {
  const rec = st.rec
  if (!rec) {
    if (st.busy) return `<section><div class="hint">${t('computing')}</div></section>`
    if (st.error) return `<section><div class="hint error">${t('stats_down')}</div></section>`
    return ''
  }
  remember(rec, st)
  let h = ''
  if (st.busy) h += `<section><div class="hint">${t('updating')}</div></section>`
  h += buyNow(st)
  if (rec.counter_picks.length) {
    h += `<section><h2>${t('counters')} <span class="note">${t('counters_note')}</span></h2>`
    h += rec.counter_picks.slice(0, 3).map(it => itemRow(it, 'counter')).join('') + '</section>'
  }
  h += `<section><h2>${t('build', { hero: esc(rec.hero_name) })} <span class="note">${t('winrate')}</span></h2>`
  for (const tier of rec.tiers) {
    if (!tier.items.length) continue
    h += `<div class="tier"><span class="cost">${tier.cost}</span><div class="items">`
    h += tier.items.slice(0, 2).map(it => itemRow(it, 'build')).join('') + '</div></div>'
  }
  h += '</section>'
  if (rec.avoid.length && !(st.owned || []).length) {
    h += `<section><h2>${t('weaker_now')} <span class="note">${t('weaker_note')}</span></h2>`
    h += rec.avoid.map(it => itemRow(it, 'avoid')).join('') + '</section>'
  }
  const since = new Date(rec.since * 1000)
  const opts = RANKS.map(([v, l]) => `<option value="${v ?? ''}" ${String(st.badge ?? '') === String(v ?? '') ? 'selected' : ''}>${v == null ? t(l) : l}</option>`).join('')
  h += `<footer><span>${t('footer', { k: (rec.matches / 1000).toFixed(0), d: `${since.getDate()}.${since.getMonth() + 1}` })} &middot; v${esc(S.version)}</span>
    <select id="rank" data-hint="${esc(t('rank_hint'))}">${opts}</select>
    ${st.view === 'match' && st.own != null ? detailsBtn() : ''}</footer>`
  return h
}

// --- interactiuni ---------------------------------------------------------------------

function bind() {
  body.querySelectorAll('[data-slot]').forEach(b => { b.onclick = () => openPicker({ slot: +b.dataset.slot }, b) })
  body.querySelectorAll('[data-manual]').forEach(b => { b.onclick = () => openPicker({ manual: b.dataset.manual }, b) })
  body.querySelectorAll('[data-item]').forEach(r => {
    r.onmouseenter = e => { e.stopPropagation(); showTip(items[r.dataset.item], r) }
    r.onmouseleave = hideTip
  })
  const more = $('#btn-details')
  if (more) more.onclick = () => { details = !details; hideTip(); render() }
  const rank = $('#rank')
  if (rank) rank.onchange = () => window.dlh.cmd({ cmd: 'badge', value: rank.value ? +rank.value : null })
}

function openPicker(target, anchor) {
  pick = target
  const st = S.state || {}
  const live = target.slot != null
  const cur = live ? st.slots?.[target.slot]?.hero
    : target.manual === 'hero' ? draft.hero : draft.enemies[+target.manual.slice(1)]
  let h = '<div class="head">'
  h += `<span>${live ? t('who_in_slot') : target.manual === 'hero' ? t('your_hero') : t('enemy')}</span><span class="grow"></span>`
  if (live) h += `<button data-act="own">${t('im_here')}</button>`
  if (cur) h += `<button data-act="clear">${t('clear')}</button>`
  h += `<button data-act="close">&#215;</button></div><div class="grid">`
  for (const hero of S.heroes) {
    h += `<button class="${hero.id === cur ? 'on' : ''}" data-hero="${hero.id}" data-hint="${esc(hero.name)}"
      style="background-image:url(${img('hero', hero.id)})"></button>`
  }
  picker.innerHTML = h + '</div>'
  picker.hidden = false
  picker.style.top = anchor.getBoundingClientRect().bottom + 4 + 'px'
  picker.querySelectorAll('[data-hero]').forEach(b => { b.onclick = () => choose(+b.dataset.hero) })
  picker.querySelector('[data-act="close"]').onclick = closePicker
  picker.querySelector('[data-act="clear"]')?.addEventListener('click', () => choose(null))
  picker.querySelector('[data-act="own"]')?.addEventListener('click', () => {
    window.dlh.cmd({ cmd: 'set_own', slot: pick.slot })
    closePicker()
  })
  measure()
}

function choose(hero) {
  if (pick.slot != null) {
    window.dlh.cmd({ cmd: 'set_slot', slot: pick.slot, hero })
  } else {
    if (pick.manual === 'hero') draft.hero = hero
    else draft.enemies[+pick.manual.slice(1)] = hero
    window.dlh.cmd({ cmd: 'manual', hero: draft.hero, enemies: draft.enemies.filter(Boolean) })
  }
  closePicker()
  render()
}

function closePicker() {
  picker.hidden = true
  pick = null
  measure()
}

function showTip(it, row) {
  if (!it) return
  const locale = S.lang === 'ro' ? 'ro-RO' : 'en-US'
  let h = `<div class="t">${esc(it.name)} <span class="l">${it.cost}</span></div>`
  h += `<div class="l">${t('tip_wr', { wr: it.wr.toFixed(1), n: it.n.toLocaleString(locale), p: it.pick.toFixed(0) })}</div>`
  if (it.buy_min) h += `<div class="l">${t('tip_buy', { m: it.buy_min })}</div>`
  if (it.imbue?.length) h += `<div class="l">${t('tip_imbue', { list: it.imbue.map(i => `${esc(i.name)} ${i.share}%`).join(', ') })}</div>`
  for (const v of it.vs_good) h += `<div class="l">${t('tip_vs', { name: esc(v.name) })} <b class="num good">${sign(v.d)}%</b></div>`
  for (const v of it.vs_bad) h += `<div class="l">${t('tip_vs', { name: esc(v.name) })} <b class="num bad">${sign(v.d)}%</b></div>`
  tip.innerHTML = h
  tip.hidden = false
  const r = row.getBoundingClientRect()
  const th = tip.offsetHeight
  // deasupra randului daca e loc, altfel dedesubt (fereastra creste dupa el)
  tip.style.top = (r.top - th - 4 > 40 ? r.top - th - 4 : r.bottom + 4) + 'px'
  measure()
}

function hideTip() {
  if (tip.hidden) return
  tip.hidden = true
  measure()
}

// --- inaltimea ferestrei = continutul (plus alegerea eroului si tooltip-ul, daca ies mai jos) ---

function measure() {
  requestAnimationFrame(() => {
    let h = $('#panel').offsetHeight
    if (!picker.hidden) h = Math.max(h, picker.getBoundingClientRect().bottom + 8)
    if (!tip.hidden) h = Math.max(h, tip.getBoundingClientRect().bottom + 8)
    window.dlh.height(h)
  })
}

new ResizeObserver(measure).observe($('#panel'))

// indiciu la hover pentru butoanele fara text
document.addEventListener('mouseover', e => {
  const el = e.target.closest('[data-hint]')
  if (!el || el.closest('[data-item]')) return
  el.title = el.dataset.hint
})
