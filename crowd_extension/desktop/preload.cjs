'use strict';
const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('CrowdHost', {postMessage: text => {
  ipcRenderer.invoke('crowd', text).then(reply => {
    // Keep the callback in the isolated preload; the main process delivers JSON only.
    if (reply) ipcRenderer.send('crowd-reply', reply);
  }).catch(() => {});
}});
