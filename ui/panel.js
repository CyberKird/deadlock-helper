'use strict'
// Panoul: deseneaza starea primita de la motor si trimite corecturile tale.

const $ = s => document.querySelector(s)
const body = $('#body'), picker = $('#picker'), tip = $('#tip')
let S = null                       // ultima stare
let draft = { hero: null, enemies: [null, null, null, null, null, null] }   // modul manual
let pick = null                    // ce slot alegi acum

const img = (kind, id) => `dlh://img/${kind}_${id}.png`
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const sign = v => (v > 0 ? '+' : '') + v.toFixed(1)
const heroName = id => S?.heroes.find(h => h.id === id)?.name || '?'

const RANKS = [[null, 'Toate rangurile'], [50, 'Ritualist+'], [60, 'Emissary+'], [70, 'Archon+'],
  [80, 'Oracle+'], [90, 'Phantom+'], [100, 'Ascendant+']]

window.dlh.onState(s => {
  S = s
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

// --- desen ---------------------------------------------------------------------------

function render() {
  const st = S.state || {}
  const view = st.view || 'loading'
  const status = $('#status')
  status.className = 'pill' + (view === 'match' ? ' live' : '')
  status.textContent = S.error ? 'eroare'
    : { loading: 'pornesc', idle: st.game?.running ? 'astept meciul' : 'jocul e inchis',
        searching: 'caut eroii', match: 'in meci', manual: 'manual' }[view] || view

  const up = $('#btn-update'), u = S.update || {}
  up.hidden = !(u.tag || u.busy || u.why)
  up.className = 'text-btn' + (u.tag ? '' : ' quiet')
  up.textContent = u.tag ? 'Update ' + u.tag : u.busy ? 'verific...' : u.why || ''
  up.dataset.hint = u.tag ? 'Reporneste pe versiunea noua' : ''

  let html = ''
  if (S.error) html += `<section><div class="hint error">${esc(S.error)}</div></section>`
  if (view === 'match' || view === 'searching') html += teamsLive(st)
  else if (view !== 'loading') html += teamsManual()
  if (view === 'loading') html += `<section><div class="hint">Incarc eroii si itemele...</div></section>`
  html += recommendation(st)
  body.innerHTML = html
  bind()
  measure()
}

function teamsLive(st) {
  const own = st.own
  const slots = st.slots || []
  const rec = st.rec
  const wr = {}
  for (const m of rec?.matchups || []) wr[m.hero] = m.wr
  const row = (from, label) => {
    let h = `<div class="team"><span class="label">${label}</span>`
    for (const s of slots.slice(from, from + 6)) {
      const cls = ['slot', s.side || '', s.you ? 'you' : '', s.manual ? 'manual' : '', s.hero ? '' : 'empty'].join(' ')
      let sub = ''
      if (s.side === 'enemy' && wr[s.hero] != null) {
        const v = wr[s.hero]
        sub = `<span class="sub ${v >= 52 ? 'good' : v <= 48 ? 'bad' : ''}">${v.toFixed(0)}%</span>`
      } else sub = `<span class="sub">${s.you ? 'tu' : ''}</span>`
      const face = s.hero ? `<span class="face" style="background-image:url(${img('hero', s.hero)})"></span>`
        : `<span class="face">?</span>`
      const hint = s.hero ? `${s.name}${s.you ? ' (tu)' : ''}. Click ca sa corectezi.` : 'Nu l-am recunoscut inca. Click ca sa-l alegi.'
      h += `<button class="${cls}" data-slot="${s.slot}" data-hint="${esc(hint)}">${face}${sub}</button>`
    }
    return h + '</div>'
  }
  const left = own == null ? 'Stanga' : own < 6 ? 'Echipa ta' : 'Inamici'
  const right = own == null ? 'Dreapta' : own < 6 ? 'Inamici' : 'Echipa ta'
  let h = `<section><h2>Echipe <span class="note">${st.view === 'searching' ? 'citesc bara de sus' : 'win rate-ul tau contra lor'}</span></h2>`
  h += row(0, left) + row(6, right)
  if (own == null && slots.some(s => s.hero)) {
    h += `<div class="hint">Nu stiu inca care esti tu. <b>Apasa pe portretul tau</b> si alege "Eu sunt aici".</div>`
  }
  return h + '</section>'
}

function teamsManual() {
  const slot = (key, id, label) => {
    const face = id ? `<span class="face" style="background-image:url(${img('hero', id)})"></span>` : '<span class="face">+</span>'
    return `<button class="slot ${id ? '' : 'empty'} ${key === 'hero' ? 'you' : 'enemy'}" data-manual="${key}"
      data-hint="${esc(id ? heroName(id) + '. Click ca sa schimbi.' : label)}">${face}<span class="sub"></span></button>`
  }
  let h = `<section><h2>Alege de mana <span class="note">pana porneste meciul</span></h2>`
  h += `<div class="team"><span class="label">Tu</span>${slot('hero', draft.hero, 'Alege eroul tau')}</div>`
  h += `<div class="team"><span class="label">Inamici</span>`
  draft.enemies.forEach((e, i) => { h += slot('e' + i, e, 'Alege un inamic') })
  h += '</div>'
  if (!draft.hero) h += `<div class="hint">In meci gasesc singur eroii din bara de sus. Pana atunci ii poti alege aici.</div>`
  return h + '</section>'
}

const imbueText = imb => imb?.length ? `imbue pe ${esc(imb[0].name)}` : ''

// Ce sa cumperi acum: primul item mare, inca doua variante, apoi ce ai deja.
function buyNow(st, rec) {
  const next = st.next || []
  const owned = st.owned || []
  if (!next.length && !owned.length) return ''
  let h = `<section class="now"><h2>Cumpara acum <span class="note">din ce ai deja</span></h2>`
  if (next.length) {
    const it = next[0]
    h += `<div class="big" data-item="${it.id}">
      <span class="ico ${it.slot}" style="background-image:url(${img('item', it.id)})"></span>
      <span class="txt"><span class="name">${esc(it.name)}</span>
        <span class="why">${esc(it.why)}</span>
        ${it.imbue ? `<span class="imbue">${imbueText(it.imbue)} (${it.imbue[0].share}% din build-uri)</span>` : ''}</span>
      <span class="cost">${it.cost}</span></div>`
    for (const alt of next.slice(1, 3)) {
      h += `<div class="row" data-item="${alt.id}">
        <span class="ico ${alt.slot}" style="background-image:url(${img('item', alt.id)})"></span>
        <span class="name">${esc(alt.name)}<span class="why">${esc(alt.why)}</span></span>
        <span class="num">${alt.cost}</span></div>`
    }
  }
  if (owned.length) {
    h += `<div class="owned"><span class="label">Ai</span><div class="chips">`
    for (const o of owned) {
      const hint = o.imbue ? `${o.name}: ${imbueText(o.imbue)} (${o.imbue[0].share}% din build-uri)` : o.name
      h += `<span class="chip ${o.slot}" data-hint="${esc(hint)}"><span class="ico ${o.slot}" style="background-image:url(${img('item', o.id)})"></span>${o.imbue ? `<span class="imb">${esc(o.imbue[0].name)}</span>` : ''}</span>`
    }
    h += '</div></div>'
  }
  return h + '</section>'
}

function itemRow(it, mode) {
  let why = '', num = ''
  if (mode === 'counter') {
    why = it.vs_good.length ? 'vs ' + it.vs_good.map(v => esc(v.name)).join(', ') : ''
    num = `<span class="num good">${sign(it.counter)}%</span>`
  } else if (mode === 'avoid') {
    why = it.vs_bad.length ? 'slab vs ' + esc(it.vs_bad[0].name) : ''
    num = `<span class="num bad">${sign(it.counter)}%</span>`
  } else {
    if (it.counter >= 1) why = 'bun contra lor'
    else if (it.counter <= -1) why = 'mai slab contra lor'
    num = `<span class="num">${it.wr.toFixed(1)}%</span>`
  }
  return `<div class="row" data-item="${it.id}">
    <span class="ico ${it.slot}" style="background-image:url(${img('item', it.id)})"></span>
    <span class="name">${esc(it.name)}${why ? `<span class="why">${why}</span>` : ''}</span>${num}</div>`
}

const items = {}

function recommendation(st) {
  const rec = st.rec
  if (!rec) {
    if (st.busy) return `<section><div class="hint">Calculez build-ul contra lor...</div></section>`
    if (st.error) return `<section><div class="hint error">${esc(st.error)}</div></section>`
    return ''
  }
  for (const k in items) delete items[k]
  const all = [...(rec.pool || []), ...rec.counter_picks, ...rec.avoid, ...rec.tiers.flatMap(t => t.items), ...(st.next || [])]
  for (const it of all) items[it.id] = { ...items[it.id], ...it }
  let h = ''
  if (st.busy) h += `<section><div class="hint">Actualizez build-ul...</div></section>`
  h += buyNow(st, rec)
  if (rec.counter_picks.length) {
    h += `<section><h2>Contra lor <span class="note">fata de cum merge de obicei</span></h2>`
    h += rec.counter_picks.slice(0, 3).map(it => itemRow(it, 'counter')).join('') + '</section>'
  }
  h += `<section><h2>Build ${esc(rec.hero_name)} <span class="note">win rate</span></h2>`
  for (const t of rec.tiers) {
    if (!t.items.length) continue
    h += `<div class="tier"><span class="cost">${t.cost}</span><div class="items">`
    h += t.items.slice(0, 2).map(it => itemRow(it, 'build')).join('') + '</div></div>'
  }
  h += '</section>'
  if (rec.avoid.length && !(st.owned || []).length) {
    h += `<section><h2>Mai slabe acum <span class="note">populare, dar nu contra lor</span></h2>`
    h += rec.avoid.map(it => itemRow(it, 'avoid')).join('') + '</section>'
  }
  const since = new Date(rec.since * 1000)
  const opts = RANKS.map(([v, l]) => `<option value="${v ?? ''}" ${String(st.badge ?? '') === String(v ?? '') ? 'selected' : ''}>${l}</option>`).join('')
  h += `<footer><span>${(rec.matches / 1000).toFixed(0)}k meciuri din ${since.getDate()}.${since.getMonth() + 1} &middot; v${esc(S.version)}</span>
    <select id="rank" data-hint="Doar meciurile de la rangul asta in sus">${opts}</select></footer>`
  return h
}

// --- interactiuni ---------------------------------------------------------------------

function bind() {
  body.querySelectorAll('[data-slot]').forEach(b => { b.onclick = () => openPicker({ slot: +b.dataset.slot }, b) })
  body.querySelectorAll('[data-manual]').forEach(b => { b.onclick = () => openPicker({ manual: b.dataset.manual }, b) })
  body.querySelectorAll('[data-item]').forEach(r => {
    r.onmouseenter = () => showTip(items[r.dataset.item], r)
    r.onmouseleave = hideTip
  })
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
  h += live ? `<span>Cine e in slotul asta?</span>` : `<span>${target.manual === 'hero' ? 'Eroul tau' : 'Inamic'}</span>`
  h += '<span class="grow"></span>'
  if (live) h += `<button data-act="own">Eu sunt aici</button>`
  if (cur) h += `<button data-act="clear">Sterge</button>`
  h += `<button data-act="close">&#215;</button></div><div class="grid">`
  for (const hero of S.heroes) {
    h += `<button class="${hero.id === cur ? 'on' : ''}" data-hero="${hero.id}" data-hint="${esc(hero.name)}"
      style="background-image:url(${img('hero', hero.id)})"></button>`
  }
  picker.innerHTML = h + '</div>'
  picker.hidden = false
  const top = anchor.getBoundingClientRect().bottom + 4
  picker.style.top = top + 'px'
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
  let h = `<div class="t">${esc(it.name)} <span class="l">${it.cost}</span></div>`
  h += `<div class="l">Win rate <b>${it.wr.toFixed(1)}%</b> in ${it.n.toLocaleString('ro-RO')} meciuri, luat in <b>${it.pick.toFixed(0)}%</b> din ele</div>`
  if (it.buy_min) h += `<div class="l">Cumparat de obicei pe la minutul <b>${it.buy_min}</b></div>`
  if (it.imbue?.length) h += `<div class="l">Imbue: <b>${it.imbue.map(i => `${esc(i.name)} ${i.share}%`).join(', ')}</b> din build-urile populare</div>`
  for (const v of it.vs_good) h += `<div class="l">Contra ${esc(v.name)}: <b class="num good">${sign(v.d)}%</b></div>`
  for (const v of it.vs_bad) h += `<div class="l">Contra ${esc(v.name)}: <b class="num bad">${sign(v.d)}%</b></div>`
  tip.innerHTML = h
  tip.hidden = false
  const r = row.getBoundingClientRect()
  const th = tip.offsetHeight
  tip.style.top = (r.top - th - 4 > 40 ? r.top - th - 4 : r.bottom + 4) + 'px'
}

function hideTip() { tip.hidden = true }

// --- inaltimea ferestrei = continutul (plus alegerea eroului, daca iese mai jos) ------------

function measure() {
  requestAnimationFrame(() => {
    let h = $('#panel').offsetHeight
    if (!picker.hidden) h = Math.max(h, picker.getBoundingClientRect().bottom + 8)
    window.dlh.height(h)
  })
}

new ResizeObserver(measure).observe($('#panel'))

// indiciu la hover pentru butoanele fara text (title nativ apare greu si urat)
document.addEventListener('mouseover', e => {
  const el = e.target.closest('[data-hint]')
  if (!el || el.closest('[data-item]')) return
  el.title = el.dataset.hint
})
