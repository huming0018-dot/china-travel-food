#!/usr/bin/env python3
"""Private, lightweight Mac acceptance kit using the participant's browser."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import re
from pathlib import Path
import zipfile
from crowd_build import ROOT, EXT, VERSION, config, extension_id, main as build_sources
from crowd_mac_trial import invitation


def write_kit(source, pilot, output):
    if not re.fullmatch('[a-f0-9]{64}',pilot.get('invite','')) or pilot.get('max_people')!=1 or pilot.get('quota_day')!=2:
        raise ValueError('Only a bounded private Mac invitation can enter this kit')
    if datetime.fromisoformat(pilot['expires_at'])<=datetime.now(timezone.utc): raise ValueError('Mac trial expired')
    with zipfile.ZipFile(source) as archive:
        files={name:archive.read(name) for name in archive.namelist()}
    manifest=json.loads(files['manifest.json'])
    manifest['background']={'service_worker':'src/background.js'}
    manifest.pop('browser_specific_settings',None)
    files['manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    conf={**config(),'platform':'macos','trialInvite':pilot['invite']}
    files['src/config.js']=('globalThis.CROWD_CONFIG = '+json.dumps(conf)+';\n').encode()
    guide='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Mac 轻量内测：从这里开始</title>
<style>body{font:18px system-ui;max-width:740px;margin:36px auto;padding:20px;line-height:1.8}code{background:#eee;padding:4px}button{padding:8px;font:inherit}</style>
<h1>Mac 轻量内测</h1><p>只使用 Chrome 或 Edge，插件约 26 KB。不需要下载浏览器运行包、运行命令或安装桌面客户端。</p>
<ol><li>解压整个包，把「Mac轻量内测」文件夹移到一个长期保留的位置。之后不要删除或移动里面的「插件」文件夹。</li>
<li>在 Chrome 地址栏输入 <code>chrome://extensions</code>；Edge 使用 <code>edge://extensions</code>。开启「开发者模式」，点击「加载已解压的扩展程序」，选择本包里的「插件」文件夹。</li>
<li>加载后会自动打开参与页面并接续邀请。勾选自愿参与，点击「同意并开始」。首次按提示登录小红书；处理登录或验证码后点「继续采集」。</li></ol>
<p>没有自动打开参与页面？点击浏览器右上角拼图图标，打开「众包公开笔记采集」。右键扩展图标选择「选项」可打开完整页面。</p>
<p>如果未显示邀请，展开「重新打开邀请」，复制下面的邀请链接、粘贴并点击「接续邀请」。无需中台邮箱或密码。</p>'''
    link=conf['portal']+'/crowd#invite='+pilot['invite']
    guide+='<textarea id="invite" readonly rows="3" style="width:100%">'+html.escape(link)+'</textarea><button onclick="const v=document.getElementById(\'invite\');v.select();document.execCommand(\'copy\');this.textContent=\'已复制邀请\'">复制邀请</button>'
    guide+='<p>仅一台 Mac，48 小时内报名，每日最多 2 条。报名截止：'+html.escape(pilot['expires_at'])+'。不要转发这个私有内测包。</p>'
    guide+='''<p>已同意并启动后，插件自动在后台领取、搜索、停留/滚动、采集及回传；可关闭参与页面、最小化浏览器窗口。浏览器进程须保持运行；没有普通窗口时插件会创建最小化的工作窗口，不主动抢焦点。</p>
<p>Mac 可以正常睡眠；睡眠中暂停，唤醒后按浏览器调度自动续做任务。浏览器退出期间不能执行，重新启动后恢复尚未停止的任务；工作页被回收会重新打开。重启或长时间挂起后重新打开页面并计时，冷却、配额和待回传证据继续保留。浏览器可能延后后台调度，不能保证固定秒数内恢复。</p>
<p>手动停止、退出参与身份、遇到登录失效、验证码或限流后保持暂停，处理后需本人点击「继续采集」，不会通过唤醒自动绕过。</p>
<p>更新已安装的插件：用本包「插件」文件夹中的文件覆盖原目录，然后在扩展管理页点击该扩展的刷新图标。不要先卸载，否则本机参与身份可能被删除，单设备邀请不能再次报名。</p>
<p>停止：重新打开插件，点击「停止」。待回传证据和进度会保留；恢复请点击「继续采集」。如果离线或回传失败，可在高级选项导出未回传证据。</p>
<p>验收：确认收到任务和至少一条真实回传；关闭参与页/最小化窗口后仍执行；让 Mac 睡眠再唤醒、退出再打开浏览器，检查任务自动继续、证据未丢失；点击停止后重复唤醒/重启，确认仍保持停止。完成后告诉 Codex「已启动」，由中台核对真实记录及标准/非标字段。</p>
<p>这是未上架、未经 Mac 实机验收的内部插件。若浏览器管理策略禁止加载，请保留提示，不修改系统或浏览器管理策略；联系 Codex。</p></html>'''
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in files.items():
            item=zipfile.ZipInfo('Mac轻量内测/插件/'+name);item.create_system=3;item.external_attr=0o100644<<16;item.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(item,data)
        archive.writestr('Mac轻量内测/先打开安装说明.html',guide)
        archive.writestr('Mac轻量内测/SHA256SUMS.txt',''.join(hashlib.sha256(data).hexdigest()+'  插件/'+name+'\n' for name,data in sorted(files.items())))
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(digest+'  '+output.name+'\n')
    return {'bytes':output.stat().st_size,'sha256':digest,'extension_id':extension_id(),'channel':'unpacked_extension','device_acceptance':False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=EXT/'releases/crowd-macos-extension-trial-v4.0.0.zip')
    args=ap.parse_args();build_sources([]);pilot=invitation()
    record=write_kit(EXT/'releases'/f'crowd-extension-v{VERSION}.zip',pilot,args.output)
    state=ROOT/'.crowd-launch';pilot['channel']='extension'
    path=state/'mac-trial.json';path.write_text(json.dumps(pilot));path.chmod(0o600)
    path=state/'mac-extension-trial-build.json';path.write_text(json.dumps(record,indent=2));path.chmod(0o600)
    print('Private Mac extension kit ready: '+str(record['bytes'])+' bytes; deploy the matching invitation service before use.')


if __name__=='__main__': main()
