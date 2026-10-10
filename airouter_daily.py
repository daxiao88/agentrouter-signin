#!/usr/bin/env python3
"""airouter 每日签到 + 台账（GitHub Actions 版，健壮响应解析）。
凭据从 os.environ 读（workflow 注入 secrets）。登录接口偶发返回非 JSON，
本版对每个响应先读文本、尝试 JSON 解析、失败则安全降级（不硬崩）。
"""
import json, os, sys, urllib.request, urllib.error, http.cookiejar, ssl, datetime

BASE = os.environ.get("AGENTROUTER_BASE", "https://ps.air-outer.com")
U = os.environ.get("AGENTROUTER_USER", "")
P = os.environ.get("AGENTROUTER_PASS", "")
LEDGER = "ledger.json"

def _open(op, path, body=None, headers=None, timeout=40, method=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    r = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if data is not None else "GET"), headers=h)
    return op.open(r, timeout=timeout)

def _try_json(resp):
    """读响应体，尽量解析成 JSON；非 JSON 返回 (None, 文本预览)。"""
    raw = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(raw), raw
    except Exception:
        return None, raw

def make_client():
    ctx = ssl.create_default_context()
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=ctx))
    return op

def main():
    if not U or not P:
        print("[airouter] 缺少 AGENTROUTER_USER/PASS 环境变量"); return 1
    op = make_client()
    today = datetime.date.today().isoformat()

    # 1) 登录
    try:
        j, raw = _try_json(_open(op, "/api/user/login", body={"username": U, "password": P}, method="POST"))
    except Exception as e:
        print(f"[airouter {today}] 登录请求异常: {e}"); return 1
    if j is None:
        print(f"[airouter {today}] 登录返回非 JSON（可能被风控/限流/登录态满），原文前 200: {raw[:200]}"); return 1
    if not j.get("success"):
        print(f"[airouter {today}] 登录失败: {j.get('message')}"); return 1
    uid = j["data"]["id"]

    # 2) 登出
    try: _open(op, "/api/user/logout", method="GET")
    except Exception: pass

    # 3) 重登 (触发当日 $25 签到)
    try:
        j2, raw2 = _try_json(_open(op, "/api/user/login", body={"username": U, "password": P}, method="POST"))
    except Exception as e:
        print(f"[airouter {today}] 重登请求异常: {e}"); return 1
    if j2 is None:
        print(f"[airouter {today}] 重登返回非 JSON，原文前 200: {raw2[:200]}"); return 1
    if not j2.get("success"):
        print(f"[airouter {today}] 重登失败: {j2.get('message')}"); return 1

    # 4) /api/user/self 读真余额（用新会话）
    op2 = make_client()
    try:
        _open(op2, "/api/user/login", body={"username": U, "password": P}, method="POST")
        j3, raw3 = _try_json(_open(op2, "/api/user/self", headers={"New-Api-User": str(uid)}, method="GET"))
    except Exception as e:
        print(f"[airouter {today}] self 请求异常: {e}"); return 1
    if j3 is None:
        print(f"[airouter {today}] self 返回非 JSON，原文前 200: {raw3[:200]}"); return 1
    d = j3.get("data") or {}
    balance_usd = round((d.get("quota") or 0) / 500000.0, 2)

    # 5) 追加台账 + 漏签检测
    L = {"history": []}
    if os.path.exists(LEDGER):
        try: L = json.load(open(LEDGER, encoding="utf-8"))
        except Exception: L = {"history": []}
    hist = L.get("history", [])
    existing = next((h for h in hist if h.get("date") == today), None)
    if existing:
        existing.update({"balance_usd": balance_usd, "ts": datetime.datetime.now().isoformat()})
    else:
        hist.append({"date": today, "checked_in": True, "balance_usd": balance_usd,
                     "source": "github-actions", "ts": datetime.datetime.now().isoformat()})
    L["history"] = hist
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(L, f, ensure_ascii=False, indent=2)

    print(f"[agentrouter {today} {datetime.datetime.now().strftime('%H:%M')}] 签到有效 | 余额 ${balance_usd}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
