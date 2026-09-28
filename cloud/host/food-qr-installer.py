#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""food-qr-installer.py（宿主机 root cron 每分钟）— 把容器扫码产出的新 cookie 装进账号目录。

容器内 /secrets/xhs_accounts 是只读挂载，无法自己写；容器把成功 cookie 写到 fooddata 卷
qr/<account>_new.json，本脚本在宿主机侧校验后安装，并把 _new.json 改名为 _installed.json
（让容器侧“new 消失”，warning_handler 据此探测 code=0 判重登成功）。
"""
import json
import os
import pathlib
import shutil

QR = pathlib.Path("/var/lib/docker/volumes/food-cloud_fooddata/_data/qr")
ACCT = pathlib.Path("/home/ubuntu/food-cloud/xhs_accounts")


def main():
    for f in QR.glob("*_new.json"):
        account = f.name[: -len("_new.json")]
        try:
            cookies = json.loads(f.read_text(encoding="utf-8"))
            names = {c.get("name") for c in cookies}
            assert isinstance(cookies, list) and len(cookies) > 5
            assert "web_session" in names and "id_token" in names
        except Exception:
            continue  # 还没写好/无效，下轮再看
        dst = ACCT / f"{account}.json"
        tmp = ACCT / f".{account}.json.tmp"
        tmp.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
        shutil.move(str(tmp), str(dst))
        shutil.chown(str(dst), user="ubuntu", group="ubuntu")
        os.chmod(dst, 0o600)
        shutil.move(str(f), str(QR / f"{account}_installed.json"))
        print("installed", account, len(cookies), flush=True)


if __name__ == "__main__":
    main()
