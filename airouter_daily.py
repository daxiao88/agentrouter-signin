#!/usr/bin/env python3
"""airouter 每日签到 + 台账（GitHub Actions 版）。
凭据从 os.environ 读（workflow 注入 secrets），不读 .env。
幂等可重跑：登录→登出→重登(触发当日$25)→/api/user/self 读真余额→追加台账。
"""
import json, os, sys, urllib.request, http.cookiejar, ssl, datetime, io, gzip

BASE = os.environ.get("AGENTROUTER_BASE", "https://ps.air-outer.com")
U = os.environ.get("AGENTROUTER_USER", "")
P = os.environ.get("AGENTROUTER_PASS", "")
LEDGER = "ledger.json"  # GitHub Actions 每次 fresh runner，每次只追加今天那条

def api():
    ctx = ssl.create_default_context()
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=ctx))
    def req(method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Content-Type": "application/json"}; h.update(headers or {})
        r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
        resp = op.open(r, timeout=40)
        return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    return req

def load_ledger():
    if os.path.exists(LEDGER):
        return json.load(open(LEDGER, encoding="utf-8"))
    return {"history": []}

def save_ledger(L):
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(L, f, ensure_ascii=False, indent=2)

def gap_days(history, today):
    dates = sorted({h["date"] for h in history} | {today})
    gaps, prev = [], None
    for d in dates:
        dt = datetime.date.fromisoformat(d)
        if prev and (dt - prev).days > 1:
            cur = prev + datetime.timedelta(days=1)
            while cur < dt:
                gaps.append(cur.isoformat()); cur += datetime.timedelta(days=1)
        prev = dt
    return gaps

def main():
    if not U or not P:
        print("[airouter] 缺少 AGENTROUTER_USER/PASS 环境变量")
        return 1
    req = api()
    today = datetime.date.today().isoformat()

    # 1) 登录
    s, j = req("POST", "/api/user/login", {"username": U, "password": P})
    if not j.get("success"):
        print(f"[airouter {today}] 登录失败: {j.get('message')}"); return 1
    uid = j["data"]["id"]

    # 2) 登出
    try: req("GET", "/api/user/logout")
    except Exception: pass

    # 3) 重登 (触发当日 $25 签到)
    s, j = req("POST", "/api/user/login", {"username": U, "password": P})
    if not j.get("success"):
        print(f"[airouter {today}] 重登失败: {j.get('message')}"); return 1

    # 4) /api/user/self 读真余额
    cj2 = http.cookiejar.CookieJar()
    op2 = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj2),
                                      urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    data = json.dumps({"username": U, "password": P}).encode()
    r = urllib.request.Request(BASE + "/api/user/login", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    op2.open(r, timeout=40)
    r = urllib.request.Request(BASE + "/api/user/self",
                               headers={"Content-Type": "application/json", "New-Api-User": str(uid)})
    resp = op2.open(r, timeout=40)
    d = json.loads(resp.read().decode("utf-8", "replace"))["data"]
    balance_usd = round((d.get("quota") or 0) / 500000.0, 2)

    # 5) 追加台账 + 漏签检测
    L = load_ledger()
    hist = L.get("history", [])
    existing = next((h for h in hist if h["date"] == today), None)
    if existing:
        existing.update({"balance_usd": balance_usd, "ts": datetime.datetime.now().isoformat()})
    else:
        hist.append({"date": today, "checked_in": True, "balance_usd": balance_usd,
                     "source": "github-actions", "ts": datetime.datetime.now().isoformat()})
    L["history"] = hist
    save_ledger(L)

    gaps = gap_days(hist, today)
    hhmm = datetime.datetime.now().strftime("%H:%M")
    gap_note = f" | 漏签日期: {','.join(gaps)}" if gaps else ""
    print(f"[agentrouter {today} {hhmm}] 签到有效 | 余额 ${balance_usd}{gap_note}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
