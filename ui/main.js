'use strict'
// Interfata Deadlock Helper: panoul peste joc si fereastra de raport. Logica e in
// motorul Python (../app.py, in exe: resources/engine/dlh-engine.exe), pornit ca
// proces copil: el scrie starea pe stdout (JSON pe linie), noi ii trimitem comenzi
// pe stdin.

const { app, BrowserWindow, ipcMain, screen, protocol, net, globalShortcut } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const { spawn } = require('node:child_process')
const { pathToFileURL } = require('node:url')
const { autoUpdater } = require('electron-updater')

const HOTKEY = 'Control+Alt+D'
const WIDTH = 340             // px CSS
const ROOT = path.join(__dirname, '..')
// setari, cache, sabloane invatate: in %APPDATA%, nu langa exe (un update il reinstaleaza)
const HOME = path.join(app.getPath('appData'), 'deadlock-helper')
fs.mkdirSync(HOME, { recursive: true })
const ICON = app.isPackaged ? path.join(process.resourcesPath, 'icon.ico') : path.join(ROOT, 'icon.ico')

const clamp = (v, a, b) => Math.max(a, Math.min(b, v))

// --- setari ---------------------------------------------------------------------

const SETTINGS = path.join(HOME, 'ui_settings.json')
let settings = {}
try { settings = JSON.parse(fs.readFileSync(SETTINGS, 'utf8')) } catch {}
function save(key, value) {
  settings[key] = value
  try { fs.writeFileSync(SETTINGS, JSON.stringify(settings, null, 1)) } catch {}
}

// --- motorul ------------------------------------------------------------------

let engine = null, quitting = false, crashes = 0, nextId = 1
let state = null, hello = null, engineError = null
const pending = new Map()

function startEngine() {
  const python = path.join(ROOT, '.venv', 'Scripts', 'python.exe')
  const [cmd, args] = app.isPackaged
    ? [path.join(process.resourcesPath, 'engine', 'dlh-engine.exe'), []]
    : [python, [path.join(ROOT, 'app.py')]]
  const env = { ...process.env, DLH_HOME: HOME, DLH_VERSION: app.getVersion(), PYTHONUNBUFFERED: '1', PYTHONUTF8: '1' }
  const child = spawn(cmd, args, { env, windowsHide: true, cwd: app.isPackaged ? HOME : ROOT })
  engine = child
  let buf = '', err = ''
  child.stdout.setEncoding('utf8')
  child.stdout.on('data', chunk => {
    buf += chunk
    let i
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim()
      buf = buf.slice(i + 1)
      if (line) onEngine(line)
    }
  })
  child.stderr.on('data', d => { err = (err + d).slice(-8000) })
  child.on('error', e => { engineError = `motorul nu porneste: ${e.code || e.message}`; push() })
  child.on('exit', code => {
    if (engine === child) engine = null
    if (quitting) return
    try { fs.writeFileSync(path.join(HOME, 'eroare.log'), `motorul s-a oprit (cod ${code})\n${err}`) } catch {}
    if (++crashes <= 3) setTimeout(startEngine, 1500 * crashes)
    else { engineError = 'motorul s-a oprit, detalii in eroare.log'; push() }
  })
}

function onEngine(line) {
  let msg
  try { msg = JSON.parse(line) } catch { return }
  if (msg.t === 'state') {
    state = msg
    engineError = null
    push()
    place()
    autoRestart()
  } else if (msg.t === 'hello') {
    hello = msg
    push()
  } else if (msg.t === 'reply' && pending.has(msg.id)) {
    pending.get(msg.id)(msg)
    pending.delete(msg.id)
  } else if (msg.t === 'error') {
    engineError = msg.text
    push()
  }
}

function command(msg) {
  if (engine && engine.stdin.writable) engine.stdin.write(JSON.stringify(msg) + '\n')
}

function ask(msg, timeout = 20000) {
  const id = nextId++
  command({ ...msg, id })
  return new Promise(resolve => {
    pending.set(id, resolve)
    setTimeout(() => { if (pending.delete(id)) resolve(null) }, timeout)
  })
}

// --- ferestre ------------------------------------------------------------------------

protocol.registerSchemesAsPrivileged([
  { scheme: 'dlh', privileges: { standard: true, secure: true, supportFetchAPI: true } },
])

// dlh://ui/<fisier> pentru interfata, dlh://img/<fisier> pentru iconitele din cache
async function serve(req) {
  const u = new URL(req.url)
  const base = u.hostname === 'img' ? hello?.img : u.hostname === 'ui' ? __dirname : null
  if (!base) return new Response('', { status: 404 })
  const file = path.resolve(base, decodeURIComponent(u.pathname).replace(/^\/+/, ''))
  if (!file.startsWith(path.resolve(base) + path.sep)) return new Response('', { status: 404 })
  try { return await net.fetch(pathToFileURL(file).toString()) } catch { return new Response('', { status: 404 }) }
}

function overlay(url, extra = {}) {
  const win = new BrowserWindow({
    show: false, frame: false, transparent: true, resizable: false, maximizable: false,
    minimizable: false, fullscreenable: false, hasShadow: false, thickFrame: false, skipTaskbar: true,
    alwaysOnTop: true, backgroundColor: '#00000000', title: 'Deadlock Helper',
    icon: fs.existsSync(ICON) ? ICON : undefined,
    // focusable: false = un click pe panou nu ia focusul jocului
    focusable: false, width: WIDTH, height: 200,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), backgroundThrottling: false, spellcheck: false },
    ...extra,
  })
  win.setAlwaysOnTop(true, 'screen-saver')
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', e => e.preventDefault())
  win.loadURL(url)
  return win
}

let panel = null
const ui = { h: 0, collapsed: false, dragging: false }

function createPanel() {
  // singura fereastra cu buton in taskbar: de acolo o fixezi (pin)
  panel = overlay('dlh://ui/panel.html', { skipTaskbar: false })
  panel.on('will-move', () => { ui.dragging = true })
  panel.on('moved', () => {
    ui.dragging = false
    const b = panel.getBounds()
    save('pos', [b.x, b.y])
  })
  panel.webContents.on('did-finish-load', () => { push(); place() })
  panel.on('closed', () => app.quit())
}

// Implicit: marginea din dreapta a ecranului jocului, putin sub bara de sus.
// L-ai mutat: ramane unde l-ai lasat (tinut in ecran).
function place() {
  if (!panel || ui.dragging || !ui.h) return
  const rect = state?.game?.rect
  const near = rect ? screen.screenToDipPoint({ x: (rect[0] + rect[2]) / 2, y: (rect[1] + rect[3]) / 2 })
    : screen.getCursorScreenPoint()
  const area = screen.getDisplayNearestPoint(near).bounds
  const h = Math.min(ui.h, area.height - 16)
  let x, y
  if (settings.pos) [x, y] = settings.pos
  else { x = area.x + area.width - WIDTH - 24; y = area.y + Math.round(area.height * 0.16) }
  const cur = screen.getDisplayNearestPoint({ x: x + 20, y: y + 20 }).bounds
  x = clamp(x, cur.x, cur.x + cur.width - WIDTH)
  y = clamp(y, cur.y, cur.y + cur.height - h)
  const b = panel.getBounds()
  if (b.x !== x || b.y !== y || b.width !== WIDTH || b.height !== h) panel.setBounds({ x, y, width: WIDTH, height: h })
  if (!panel.isVisible()) panel.showInactive()
}

function push() {
  if (!panel || panel.isDestroyed()) return
  panel.webContents.send('state', {
    state, heroes: hello?.heroes || [], error: engineError, collapsed: ui.collapsed, hotkey: 'CTRL+ALT+D',
    version: app.getVersion(), update: { tag: update.tag, busy: update.busy, why: update.why },
  })
}

ipcMain.on('height', (_e, h) => { ui.h = Math.max(40, Math.round(h)); place() })
ipcMain.on('cmd', (_e, c) => {
  if (!c || typeof c !== 'object') return
  if (c.cmd === 'close') app.quit()
  else if (c.cmd === 'collapse') toggle()
  else if (c.cmd === 'home') { save('pos', null); place() }
  else if (c.cmd === 'report') openReport()
  else if (c.cmd === 'update') update.tag ? restart() : checkUpdate(true)
  else if (['set_slot', 'set_own', 'reset', 'manual', 'badge', 'refresh'].includes(c.cmd)) command(c)
})

function toggle() {
  ui.collapsed = !ui.collapsed
  push()
}

// --- raportul de bug ------------------------------------------------------------------
// Fereastra proprie, pe mijlocul ecranului pe care e panoul. Poate lua focus:
// are campuri de scris.

let report = null

function openReport() {
  if (report) { report.show(); report.focus(); return }
  report = overlay('dlh://ui/report.html', { focusable: true, title: 'Raporteaza o problema', width: 420 })
  report.on('closed', () => { report = null })
}

ipcMain.handle('report-init', async () => {
  const diag = await ask({ cmd: 'diag' }, 5000)
  return { diag: diag?.text || '(motorul nu a raspuns)', version: app.getVersion() }
})

ipcMain.on('report-size', (_e, s) => {
  if (!report || !s) return
  const a = screen.getDisplayMatching(panel.getBounds()).workArea
  const w = Math.min(Math.round(s.w), a.width - 16), h = Math.min(Math.round(s.h), a.height - 16)
  if (!report.isVisible()) {
    report.setBounds({ x: Math.round(a.x + (a.width - w) / 2), y: Math.round(a.y + (a.height - h) / 2), width: w, height: h })
    report.show()
    report.focus()
  } else {
    const b = report.getBounds()
    report.setBounds({ x: b.x, y: clamp(b.y, a.y, a.y + a.height - h), width: w, height: h })
  }
})

ipcMain.handle('report-send', (_e, r) => ask({ cmd: 'report', desc: String(r?.desc || ''),
  email: String(r?.email || ''), diag: r?.include ? String(r.diag || '') : '(diagnostic omis de utilizator)' }))
ipcMain.on('report-mailto', (_e, r) => command({ cmd: 'mailto', desc: String(r?.desc || ''), diag: String(r?.diag || '') }))
ipcMain.on('report-close', () => report?.close())

// --- update-uri -------------------------------------------------------------------------
// Se descarca singure in fundal (doar diferenta) si se instaleaza cand inchizi
// aplicatia. Cand jocul nu ruleaza, repornim singuri pe versiunea noua.

const update = { tag: null, busy: false, why: null, manual: false }

function checkUpdate(manual) {
  if (!app.isPackaged || update.tag || update.busy) return
  Object.assign(update, { busy: manual, why: null, manual })
  push()
  autoUpdater.checkForUpdates().catch(() => {})
}

function finishCheck(why) {
  if (update.manual) Object.assign(update, { busy: false, why, manual: false })
  push()
}

autoUpdater.autoInstallOnAppQuit = true
autoUpdater.on('update-downloaded', info => {
  Object.assign(update, { tag: 'v' + info.version, busy: false })
  push()
})
autoUpdater.on('update-not-available', () => finishCheck('esti la zi'))
autoUpdater.on('error', e => finishCheck('eroare: ' + (e.code || e.name || 'update')))

function restart() {
  if (!update.tag) return
  quitting = true
  autoUpdater.quitAndInstall(true, true)
}

function autoRestart() {
  if (update.tag && !state?.game?.running && settings.restarted_for !== update.tag) {
    save('restarted_for', update.tag)
    restart()
  }
}

// --- pornire ----------------------------------------------------------------------------

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.setAppUserModelId('com.joltarise.deadlockhelper')
  app.on('second-instance', () => { ui.collapsed = false; push(); panel?.showInactive() })
  app.whenReady().then(() => {
    protocol.handle('dlh', serve)
    startEngine()
    createPanel()
    globalShortcut.register(HOTKEY, toggle)
    screen.on('display-metrics-changed', place)
    if (!process.argv.includes('--no-update')) {
      checkUpdate(false)
      setInterval(() => checkUpdate(false), 30 * 60 * 1000)
    }
    // test: DLH_SHOT=<fisier.png> salveaza panoul dupa cateva secunde si inchide
    if (process.env.DLH_SHOT) {
      if (process.env.DLH_SHOT_REPORT) setTimeout(openReport, 4000)
      setTimeout(async () => {
        const win = process.env.DLH_SHOT_REPORT ? report : panel
        const shot = await win.webContents.capturePage()
        fs.writeFileSync(process.env.DLH_SHOT, shot.toPNG())
        app.quit()
      }, +(process.env.DLH_SHOT_MS || 8000))
    }
  })
  app.on('before-quit', () => {
    quitting = true
    command({ cmd: 'quit' })
    engine?.stdin.end()                   // stdin inchis = motorul iese singur
  })
  app.on('window-all-closed', () => app.quit())
  app.on('will-quit', () => globalShortcut.unregisterAll())
}
