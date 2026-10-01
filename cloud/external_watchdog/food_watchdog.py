#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""food_watchdog.py — 外部入站健康探针 + 自动关机/开机自愈。

部署在独立于 food 的代理盒（广州），定时 TCP 探测 food 公网 IP 的 22 端口：
  - 可达：健康，复位计数。
  - 不可达且 Lighthouse DescribeInstances 显示非 RUNNING：属正常关机/开机/重启窗口，不动作。
  - 不可达且实例 RUNNING：这是“公网 NAT 映射陈旧”的特征（Reboot 无效），
    满足【连续 N 个周期失败 + 距上次重启已过冷却】后自动 Stop→Start 重建公网绑定，
    轮询至 RUNNING 且 22 恢复；触发与恢复均推 Telegram + 飞书。

状态持久化在 wd_state.json（连续失败数、上次重启时间、是否已通告），防 flapping。
cron 用 flock 包裹，保证同一时刻只有一个实例。
"""
import json
import os
import pathlib
import socket
import sys
import time

sys.path.insert(0, "/home/ubuntu/wdlib")
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.lighthouse.v20200324 import lighthouse_client, models

import wd_notify as N

HERE = pathlib.Path(__file__).resolve().parent
STATE_F = HERE / "wd_state.json"

# ---- 参数
ATTEMPTS = 3          # 单轮内 TCP 重试次数（防瞬断）
ATTEMPT_GAP = 5
NEED_BAD_CYCLES = 2   # 连续多少个周期失败才重启
RECYCLE_COOLDOWN = 900
TITLE = "上海美食图鉴·入站看门狗"

# 从 wd.env 读 food 实例参数
def load_conf():
    env = {}
    for name in ("wd.env",):
        p = HERE / name
        if p.exists():
            for line in p.read_text().splitlines():
                k, _, v = line.strip().partition("=")
                if k:
                    env[k] = v
    return env

CONF = load_conf()
REGION = CONF.get("FOOD_REGION", "ap-shanghai")
IID = CONF.get("FOOD_INSTANCE_ID", "lhins-5uumzybo")
HOST = CONF.get("FOOD_PUBLIC_IP", "49.234.35.92")
SID = CONF["TENCENT_SECRET_ID"]
SK = CONF["TENCENT_SECRET_KEY"]

cli = lighthouse_client.LighthouseClient(
    credential.Credential(SID, SK), REGION,
    ClientProfile(httpProfile=HttpProfile(
        endpoint="lighthouse.tencentcloudapi.com", reqTimeout=20)))


def tcp_ok(port=22, timeout=6):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((HOST, port)) == 0
    finally:
        s.close()


def instance_state():
    r = models.DescribeInstancesRequest(); r.InstanceIds = [IID]
    return cli.DescribeInstances(r).InstanceSet[0].InstanceState


def wait_state(target, tries, gap):
    for _ in range(tries):
        time.sleep(gap)
        try:
            if instance_state() == target:
                return True
        except Exception:
            pass
    return False


def recycle():
    print("stopping...")
    s = models.StopInstancesRequest(); s.InstanceIds = [IID]
    try:
        cli.StopInstances(s)
    except Exception as e:
        print("stop err", str(e)[:120])
    if not wait_state("STOPPED", 30, 5):
        print("did not reach STOPPED")
    time.sleep(15)  # 等平台操作收尾
    print("starting...")
    st = models.StartInstancesRequest(); st.InstanceIds = [IID]
    started = False
    for k in range(10):
        try:
            cli.StartInstances(st); started = True; break
        except Exception as e:
            print("start retry", k, str(e)[:80]); time.sleep(10)
    if not started:
        return False
    if not wait_state("RUNNING", 40, 5):
        print("did not reach RUNNING")
    for _ in range(30):  # 等 sshd/NAT 就绪，最多 ~180s
        time.sleep(6)
        if tcp_ok():
            return True
    return False


def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text())
        except Exception:
            pass
    return {}


def save_state(st):
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def main():
    st = load_state()
    healthy = False
    for i in range(ATTEMPTS):
        if tcp_ok():
            healthy = True
            break
        time.sleep(ATTEMPT_GAP)

    if healthy:
        if st.get("was_down"):
            N.send(TITLE, "food 公网 22 已恢复，入站链路正常。无需操作。")
        st.update(bad=0, was_down=False, announced_pending=False)
        save_state(st)
        print("healthy")
        return

    # 不可达：先看实例真实状态
    try:
        ist = instance_state()
    except Exception as e:
        print("describe err", e)
        return
    if ist != "RUNNING":
        print(f"instance {ist}: normal window, no action")
        return

    st["bad"] = int(st.get("bad", 0)) + 1
    now = time.time()
    last = float(st.get("last_recycle", 0))
    if st["bad"] >= NEED_BAD_CYCLES and now - last >= RECYCLE_COOLDOWN:
        N.send(TITLE, f"food 实例 RUNNING 但公网 22 连续 {st['bad']} 个周期不可达，"
                       "判定公网 NAT 映射陈旧，正在自动 Stop/Start 重建绑定。无需操作。")
        st["last_recycle"] = now
        save_state(st)
        ok = recycle()
        if ok:
            N.send(TITLE, "已自动 Stop/Start，food 公网 22 恢复可达。无需操作。")
            st.update(bad=0, was_down=False, announced_pending=False)
        else:
            N.send(TITLE, "自动 Stop/Start 后 food 公网 22 仍不可达，需人工检查"
                           "（控制台/OrcaTerm）。唯一动作：人工核查实例网络。")
            st.update(was_down=True, announced_pending=True)
    else:
        if not st.get("announced_pending"):
            N.send(TITLE, f"food 实例 RUNNING 但公网 22 不可达，第 {st['bad']} 次确认；"
                           "满足连续失败与冷却后将自动 Stop/Start。无需操作。")
            st["announced_pending"] = True
    save_state(st)
    print("unreachable, bad cycles =", st["bad"])


if __name__ == "__main__":
    main()
