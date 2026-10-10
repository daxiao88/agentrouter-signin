#!/usr/bin/env python3
"""airouter 每日签到 + 台账（多域名回退 + 健壮响应解析）。
凭据从 os.environ 读（workflow 注入 secrets）。
域名策略：依次尝试 [国内域 ps.air-outer.com, 海外域 agentrouter.org]，
  哪个能登录成功就用哪个；国内域常被阿里云 WAF 拦（返回 aliyun_waf HTML 页），
  海外域 agentrouter.org 无 WAF，海外 runner 走它一般能拿到正常 JSON。
每个响应先读文本、尝试 JSON 解析、失败则安全降级（不硬崩），并打印原文前 200 便于诊断。
"""
import json, os, sys, urllib.request, urllib.error, http.cookiejar, ssl, datetime

# 多域回退（顺序=优先级）；可用环境变量 AGENTROUTER_BASES 覆盖（逗号分隔）
DEFAULT_BASES = ["https://ps.air-outer.com", "https://agentrouter.org"]
BASES = [b.strip() for b in os.environ.get("AGENTROUTER_BASES", ",".join(DEFAULT_BASES)).split(",") if b.strip()]
U = os.environ.get("AGENTROUTER_USER", "")
P = os.environ.get("AGENTROUTER_PASS", "")
LEDGER = "ledger.json"

def make_client():
    ctx = ssl.create_default_context()
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                       urllib.request.HTTPSHandler(context=ctx))

def _post(op, base, path, body, timeout=40):
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    r = urllib.request.Request(base + path, data=data, method="POST", headers=h)
    return op.open(r, timeout=timeout).read().decode("utf-8", "replace")

def _get(op, base, path, headers=None, timeout=40):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    r = urllib.request.Request(base + path, method="GET", headers=h)
    return op.open(r, timeout=timeout).read().decode("utf-8", "replace")

def _parse(raw):
    try:
        return json.loads(raw), raw
    except Exception:
        return None, raw

def try_signin(base):
    """在 base 上跑完整签到。成功返回 (True, 余额, 摘要)；失败返回 (False, 原因, 摘要)。"""
    op = make_client()
    today = datetime.date.today().isoformat()

    # 1) 登录
    raw = _post(op, base, "/api/user/login", {"username": U, "password": P})
    j, _ = _parse(raw)
    if j is None:
        waf = "aliyun_waf" in raw[:500] or "<!doctype" in raw[:50].lower()
        return False, f"登录返回非JSON{'(WAF拦截)' if waf else ''}", raw[:150].replace("\n", " ")
    if not j.get("success"):
        return False, f"登录失败: {j.get('message')}", j.get("message") or ""
    uid = j["data"]["id"]

    # 2) 登出
    try: _get(op, base, "/api/user/logout")
    except Exception: pass

    # 3) 重登 (触发当日 $25 签到)
    raw2 = _post(op, base, "/api/user/login", {"username": U, "password": P})
    j2, _ = _parse(raw2)
    if j2 is None:
        return False, f"重登返回非JSON", raw2[:150].replace("\n", " ")
    if not j2.get("success"):
        return False, f"重登失败: {j2.get('message')}", j2.get("message") or ""

    # 4) /api/user/self 读真余额
    op2 = make_client()
    _post(op2, base, "/api/user/login", {"username": U, "password": P})  # 刷新 op2 会话
    raw3 = _get(op2, base, "/api/user/self", headers={"New-Api-User": str(uid)})
    j3, _ = _parse(raw3)
    if j3 is None:
        return False, f"self返回非JSON", raw3[:150].replace("\n", " ")
    d = j3.get("data") or {}
    balance_usd = round((d.get("quota") or 0) / 500000.0, 2)

    # 5) 追加台账
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

    hhmm = datetime.datetime.now().strftime("%H:%M")
    return True, balance_usd, f"{base} 登录成功 余额${balance_usd}"

def main():
    if not U or not P:
        print("[airouter] 缺少 AGENTROUTER_USER/PASS 环境变量"); return 1
    today = datetime.date.today().isoformat()

    last_fail = ""
    for base in BASES:
        try:
            ok, bal, info = try_signin(base)
        except urllib.error.HTTPError as e:
            last_fail = f"{base}: HTTP {e.code}"
            print(f"[airouter {today}] {last_fail} => 试下一域"); continue
        except Exception as e:
            last_fail = f"{base}: {type(e).__name__} {str(e)[:80]}"
            print(f"[airouter {today}] {last_fail} => 试下一域"); continue
        if ok:
            print(f"[agentrouter {today} {datetime.datetime.now().strftime('%H:%M')}] 签到有效 | 余额 ${bal} | 使用域名 {base}")
            return 0
        else:
            last_fail = f"{base}: {info}"
            print(f"[airouter {today}] {base} 失败: {info} => 试下一域")

    print(f"[agentrouter {today}] ⚠️ 所有域名({len(BASES)})均失败: {last_fail}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
