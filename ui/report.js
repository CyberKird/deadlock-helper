'use strict'
// Raportul de bug: textul tau, emailul (optional) si, doar daca lasi bifat,
// diagnosticul pe care il vezi aici inainte sa plece. Fara capturi de ecran.

const $ = id => document.getElementById(id)
const api = window.dlh
let diag = ''

function translate(l) {
  setLang(l)
  document.documentElement.lang = l
  document.querySelectorAll('[data-t]').forEach(el => { el.textContent = t(el.dataset.t) })
  $('desc').placeholder = t('report_placeholder')
  $('close').title = t('report_close_hint')
  resize()
}

function resize() {
  const r = $('panel').getBoundingClientRect()
  api.send('report-size', { w: Math.ceil(r.width), h: Math.ceil(r.height) })
}

function result(text, ok) {
  $('result').textContent = text
  $('result').className = ok ? 'ok' : 'bad'
  resize()
}

api.invoke('report-init').then(init => {
  diag = init.diag
  $('diag').textContent = diag
  translate(init.lang)
  $('desc').focus()
})
api.onLang(translate)

$('form').addEventListener('submit', async e => {
  e.preventDefault()
  const send = $('send')
  if (send.disabled) return
  send.disabled = true
  send.textContent = t('report_sending')
  const r = await api.invoke('report-send', {
    desc: $('desc').value, email: $('email').value, include: $('include').checked, diag,
  })
  send.disabled = false
  send.textContent = t('report_send')
  if (!r) return result(t('report_no_engine'), false)
  result(r.text, r.ok)
  if (r.ok) setTimeout(() => api.send('report-close'), 1500)
  else if (r.kind === 'send') {
    $('mail').hidden = false          // rezerva, doar dupa un esec de trimitere
    resize()
  }
})

$('mail').addEventListener('click', () => api.send('report-mailto', {
  desc: $('desc').value, diag: $('include').checked ? diag : '(diagnostics left out by the user)',
}))
$('close').addEventListener('click', () => api.send('report-close'))
document.addEventListener('keydown', e => { if (e.key === 'Escape') api.send('report-close') })
new ResizeObserver(resize).observe($('panel'))
