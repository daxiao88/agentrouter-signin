#!/usr/bin/env python3
"""airouter 每日签到 + 台账 + 漏签检测（curl_cffi 版，绕过阿里云 WAF）。
闭环：登录 → 登出 → 重登(触发当日 $25) → /api/user/self 读真余额 → 追加台账 → 漏签检测。
每天 1 次、4 个 HTTP 调用，幂等可重跑。脚本级 cron 用。
余额真相源：/api/user/self 的 quota ÷500000 = 美元（与 bsk 看板吻合，勿用登录返回的 quota=0）。
依赖：curl_cffi>=0.15.0（pip install curl_cffi，Hermes venv 已装）。
"""
import json, os, sys, datetime
from curl_cffi import requests

ENV = os.path.expanduser("~") + r"\AppData\Local\hermes\.env"
BASE = "https://ps.air-outer.com"
LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agentrouter_checkin_ledger.json")
CREDIT = 25.0
IMPERSONATE = "chrome"  # curl_cffi 指纹：chrome / chrome124 / safari / edge 等

def load_env():
    env = {}
    for l in open(ENV, encoding="utf-8"):
        l = l.rstrip("\r\n")
        if "=" in l and not l.lstrip().startswith("#"):
            k, v = l.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def load_ledger():
    if os.path.exists(LEDGER):
        return json.load(open(LEDGER, encoding="utf-8"))
    return {"history": []}

def save_ledger(L):
    json.dump(L, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def gap_days(history, today):
    """返回连续漏签日期列表。history 日期升序。"""
    dates = sorted({h["date"] for h in history} | {today})
    gaps, prev = [], None
    for d in dates:
        dt = datetime.date.fromisoformat(d)
        if prev and (dt - prev).days > 1:
            cur = prev + datetime.timedelta(days=1)
            while cur < dt:
                gaps.append(cur.isoformat())
                cur += datetime.timedelta(days=1)
        prev = dt
    return gaps

def main():
    env = load_env()
    U, P = env.get("AGENTROUTER_USER", ""), env.get("AGENTROUTER_PASS", "")
    today = datetime.date.today().isoformat()

    # 统一 session（curl_cffi 自动处理 cookie）
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})

    def req(method, path, body=None):
        url = BASE + path
        data = json.dumps(body) if body is not None else None
        r = s.request(method, url, data=data, impersonate=IMPERSONATE, timeout=40)
        return r.status_code, r.json()

    # 1) 登录
    status, j = req("POST", "/api/user/login", {"username": U, "password": P})
    if not j.get("success"):
        print(f"[agentrouter {today}] API登录失败: {j.get('message')}")
        return 1
    uid = j["data"]["id"]

    # 2) 登出
    try:
        req("GET", "/api/user/logout")
    except Exception:
        pass

    # 3) 重登 (触发当日 $25 签到)
    status, j = req("POST", "/api/user/login", {"username": U, "password": P})
    if not j.get("success"):
        print(f"[agentrouter {today}] 重登失败: {j.get('message')}")
        return 1

    # 4) /api/user/self 读真余额（带 New-Api-User header）
    r = s.get(BASE + "/api/user/self", headers={"New-Api-User": str(uid)}, impersonate=IMPERSONATE, timeout=40)
    d = r.json()["data"]
    quota = d.get("quota") or 0
    balance_usd = round(quota / 500000.0, 2)

    # 5) 追加台账 + 漏签检测
    L = load_ledger()
    hist = L.get("history", [])
    existing = next((h for h in hist if h["date"] == today), None)
    if existing:
        existing.update({"balance_usd": balance_usd, "ts": datetime.datetime.now().isoformat()})
    else:
        hist.append({"date": today, "checked_in": True, "balance_usd": balance_usd,
                     "source": "airouter_daily.py", "ts": datetime.datetime.now().isoformat()})
    L["history"] = hist
    save_ledger(L)

    # 6) 漏签提醒 + 报告 (含 签到时间 HH:MM 与 漏签日期)
    gaps = gap_days(hist, today)
    now = datetime.datetime.now()
    hhmm = now.strftime("%H:%M")
    gap_note = ""
    if gaps:
        gap_note = f" | 漏签日期: {','.join(gaps)}"
    print(f"[agentrouter {today} {hhmm}] 签到有效 | 余额 ${balance_usd} | 本次签到时间 {hhmm}{gap_note}")
    return 0

if __name__ == "__main__":
    sys.exit(main())