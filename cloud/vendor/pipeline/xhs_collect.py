#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xhs_collect.py — 小红书真实食客证据采集（在登录态浏览器上，串行、断点续跑）。

关键：必须用真实坐标点击（CDP 鼠标）让 URL 带 xsec_token，JS click 会被风控（见教训 #54）。
本模块只提供"机械动作 + 提取"，在 mac_computer_use_tool(plane=bu) cell 内 import 调用；
"哪篇是堂食实质"用 common.quote_has_substance 判断。
"""
import json
import pathlib
from urllib.parse import quote


def search(bu, keyword, city="上海"):
    bu.navigate("https://www.xiaohongshu.com/search_result?keyword=" + quote(f"{keyword} {city}"))
    bu.wait_for_load(timeout=15)
    bu.wait(2.2)


def note_positions(bu, limit=12):
    """搜索结果笔记封面坐标（0-1000 归一）+ 标题。
    必须等到【布局完成】：DOM 刚挂载时卡片会堆叠在同一个 rect（实测多个卡片 x/y/宽高完全相同），
    只数卡片数量会导致每篇都点到同一位置。判据 = 卡片数够 + 宽高正常 + 中心坐标去重后不重叠。"""
    vw = bu.js("return {w:innerWidth,h:innerHeight};")
    extract = """
    const els=[...document.querySelectorAll('section.note-item')];
    const items=els.slice(0,%d).map(el=>{
      const cover=el.querySelector('a.cover,.cover');
      const t=el.querySelector('.title,.footer .title,a[title]');
      const r=(cover||el).getBoundingClientRect();
      let title=t?t.innerText:'';
      if(!title){const lines=el.innerText.split('\\n').filter(Boolean); title=lines[0]||'';}
      return {px:Math.round(r.x+r.width/2),py:Math.round(r.y+r.height/2),
              w:Math.round(r.width),h:Math.round(r.height),title};
    });
    const distinct=new Set(items.map(n=>n.px+'_'+n.py)).size;
    const laid=items.length>=3 && items.every(n=>n.w>50&&n.h>50) && distinct>=3;
    return {items,laid,total:els.length};
    """ % limit
    items = []
    for _ in range(13):  # 最多约 13 秒等布局完成
        o = bu.js(extract)
        items = o.get("items", [])
        if o.get("laid"):
            break
        if o.get("total", 0) < 3 and items:  # 结果本身不足 3（极少数）
            break
        bu.wait(1.0)
    out = []
    for n in items:
        if n["w"] <= 50 or n["h"] <= 50:
            continue
        out.append({"title": n["title"],
                    "x": round(n["px"] / vw["w"] * 1000),
                    "y": round(n["py"] / vw["h"] * 1000)})
    return out


def open_note(bu, x, y):
    bu.click_xy(x, y)
    bu.wait(2.2)
    return bu.js(r"""
    const blocked=/当前笔记暂时无法浏览/.test(document.body.innerText);
    const note=document.querySelector('#noteContainer');
    if(blocked||!note) return {ok:false};
    const q=s=>{const e=document.querySelector(s);return e?e.innerText:'';};
    return {ok:true, title:q('#detail-title'), author:q('.author-wrapper .name'),
      date:q('.date'), desc:q('#detail-desc'), url:location.href};
    """)


def scroll_and_get_comments(bu, rounds=5):
    for _ in range(rounds):
        bu.js("const sc=document.querySelector('.note-scroller'); if(sc) sc.scrollTop=sc.scrollHeight;")
        bu.wait(0.7)
    return bu.js(r"""
    return [...document.querySelectorAll('.comment-item')].map(c=>{
      const n=c.querySelector('.name,.user-name,.author');
      const t=c.querySelector('.note-text,.content');
      return {name:(n?n.innerText:'').trim().replace('作者','').trim(),
              text:(t?t.innerText:'').trim()};
    }).filter(x=>x.text && x.text.length<600);
    """)


def close_note(bu):
    bu.js("const x=document.querySelector('.close-box'); if(x)x.click();")
    bu.wait(0.9)


def collect_restaurant(bu, name, max_notes=4, city="上海"):
    """采集一家店：返回 {name, notes:[{title,author,date,desc,url,comments}]}。"""
    search(bu, name, city)
    positions = note_positions(bu, limit=max_notes + 3)
    notes, opened = [], 0
    for p in positions:
        if opened >= max_notes:
            break
        info = open_note(bu, p["x"], p["y"])
        if not info.get("ok"):
            continue
        comments = scroll_and_get_comments(bu)
        close_note(bu)
        opened += 1
        notes.append({"title": info["title"], "author": info["author"], "date": info["date"],
                      "desc": info["desc"], "url": info["url"], "comments": comments})
    return {"name": name, "notes": notes}


def append_jsonl(path, record):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
