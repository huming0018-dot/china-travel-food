#!/usr/bin/env python3
"""Read-only, task-scoped dependency checks. Does not inspect cookies or log in."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--channel", choices=["public","dianping","media"], default="public")
    p.add_argument("--media-root")
    args = p.parse_args()
    checks = {"python_3_11_or_newer": sys.version_info >= (3,11),
              "host_public_search": "host must confirm actual search/read tools; not probed here"}
    ready = checks["python_3_11_or_newer"]
    if args.channel == "dianping":
        checks["playwright_installed"] = importlib.util.find_spec("playwright") is not None
        checks["chromium_present"] = False
        if checks["playwright_installed"]:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    checks["chromium_present"] = Path(p.chromium.executable_path).is_file()
            except Exception:
                checks["browser_probe"] = "failed"
        checks["login"] = "not_probed; cookies do not prove valid login"
        ready = ready and checks["playwright_installed"] and checks["chromium_present"]
    if args.channel == "media":
        root = args.media_root or str(Path(__file__).resolve().parent.parent / "tools" / "media-crawler")
        checks["media_root"] = root
        checks["external_main_py"] = (Path(root) / "main.py").is_file()
        venv_py = Path(root) / ".venv" / "bin" / "python"
        checks["media_venv"] = venv_py.is_file()
        checks["node_present"] = shutil.which("node") is not None
        checks["node_path"] = shutil.which("node")
        if checks["node_present"]:
            # 抖音签名依赖 execjs→Nashorn；JDK15+ 已移除 Nashorn，故 Node 才是正解。
            checks["node_required_for"] = "douyin signature (execjs/Nashorn); JDK will NOT work"
        # 登录态：只报告 cookie 是否落盘，明确不等于会话有效（2026-10-18 实测过期）
        for plat, ck in (("xhs", "web_session"), ("dy", "sessionid")):
            db = Path(root) / "browser_data" / f"{plat}_user_data_dir" / "Default" / "Cookies"
            present = False
            if db.is_file():
                try:
                    import sqlite3 as _sq, tempfile as _tf
                    tmpd = _tf.mkdtemp()
                    tmp = Path(tmpd) / "C.db"
                    tmp.write_bytes(db.read_bytes())
                    with _sq.connect(tmp) as con:
                        present = con.execute(
                            "SELECT COUNT(*) FROM cookies WHERE name=? AND "
                            "(length(value)>0 OR length(encrypted_value)>0)", (ck,)
                        ).fetchone()[0] > 0
                    tmp.unlink(missing_ok=True)
                    shutil.rmtree(tmpd, ignore_errors=True)
                except Exception as exc:
                    present = "read_failed: %s" % type(exc).__name__
            checks[f"{plat}_login_cookie_present"] = present
        checks["platform_login"] = "NOT VERIFIED — cookie present != valid session; run an actual collect"
        ready = ready and checks["external_main_py"] and checks["node_present"]
    print(json.dumps({"channel": args.channel, "checks":checks, "local_dependencies_ready":ready,
                      "note":"Readiness is local only. Optional failure does not disable host public search."},ensure_ascii=False,indent=2))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
