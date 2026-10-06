"""Export only public invitation material for the owner; never embed deployment credentials."""
import base64
import html
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

NAMES={'android':'安卓 / 兼容安卓的华为','windows':'Windows','macos':'Mac','ios':'iPhone / iPad','harmony':'原生鸿蒙'}


def write_share(invitation, destination, platforms):
    link=invitation['link']; url=urlsplit(link)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.path!='/crowd' or url.query or not re.fullmatch(r'invite=[a-f0-9]{64}',url.fragment):
        raise ValueError('Invalid invitation link')
    qr=invitation['qr']
    if not re.fullmatch(r'data:image/png;base64,[A-Za-z0-9+/=]+',qr): raise ValueError('Invalid invitation QR')
    image=base64.b64decode(qr.split(',',1)[1],validate=True)
    if not image.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('Invalid PNG QR')
    text='邀请你自愿参加公开笔记研究。点链接安装并打开客户端，同意参与、首次登录小红书后自动执行，可随时停止：\n'+link
    devices='、'.join(NAMES[p] for p in platforms if p in NAMES)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'"><title>发给朋友</title><style>body{font:18px system-ui;margin:32px auto;padding:20px;max-width:560px;line-height:1.6}textarea{box-sizing:border-box;width:100%;min-height:180px;font:inherit}button,a{display:inline-block;margin:12px 12px 12px 0;padding:14px;border:1px solid #ccc;border-radius:12px}button{background:#df2445;color:white}img{max-width:100%}</style><h1>复制这条短信，发给朋友</h1><p>同一条链接或二维码可以转发。安装指引会按设备显示。参与者完成同意和首次登录后自动执行。</p><p>现在可用：DEVICES</p><textarea id="sms" readonly aria-label="分发短信">SMS</textarea><button id="copy">复制整条短信</button><a href="SMS_URL">用短信发送</a><p id="message" role="status"></p><img src="QR" alt="参与邀请二维码" width="320"><p>也可以发送同目录的 invite-qr.png。保留这份页面，再次分发直接打开即可。</p><p>到期：EXPIRY。同一邀请的名额和期限仍按这一批计算。</p><script>document.getElementById('copy').onclick=async()=>{const t=document.getElementById('sms');try{await navigator.clipboard.writeText(t.value);document.getElementById('message').textContent='已复制，粘贴发给朋友即可。'}catch{t.focus();t.select();document.getElementById('message').textContent='短信已选中，请按复制，再粘贴发送。'}};</script></html>'''
    page=page.replace('DEVICES',html.escape(devices))
    page=page.replace('>SMS<','>'+html.escape(text)+'<')
    page=page.replace('href="SMS_URL"','href="'+html.escape('sms:?body='+quote(text),quote=True)+'"')
    page=page.replace('src="QR"','src="'+html.escape(qr,quote=True)+'"')
    page=page.replace('EXPIRY',html.escape(str(invitation['expires_at'])))
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for name,data in [('invite-link.txt',(link+'\n').encode()),('invite-sms.txt',(text+'\n').encode()),('invite-qr.png',image),('发给朋友.html',page.encode())]:
        temporary=destination/(name+'.tmp');temporary.write_bytes(data);temporary.replace(destination/name)
    return destination/'发给朋友.html'
