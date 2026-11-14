'use strict'
// Puntea dintre pagini si procesul principal: doar canalele de mai jos.
const { contextBridge, ipcRenderer } = require('electron')

const SEND = ['height', 'cmd', 'report-size', 'report-mailto', 'report-close']
const INVOKE = ['report-init', 'report-send']

contextBridge.exposeInMainWorld('dlh', {
  onState: fn => ipcRenderer.on('state', (_e, s) => fn(s)),
  cmd: c => ipcRenderer.send('cmd', c),
  height: h => ipcRenderer.send('height', h),
  send: (ch, data) => { if (SEND.includes(ch)) ipcRenderer.send(ch, data) },
  invoke: (ch, data) => INVOKE.includes(ch) ? ipcRenderer.invoke(ch, data) : Promise.reject(new Error(ch)),
})
