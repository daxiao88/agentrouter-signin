# airouter-signin（GitHub Actions 每日签到）

agentrouter（`ps.air-outer.com`）每日签到自动化。每天 00:30（北京时间，早于本机 08:00）跑一次，触发 airouter 当日 **+$25 签到奖励**。纯 Python 单文件，无第三方依赖，GitHub Actions 托管 7×24（电脑关机也不漏签）。

> **免费**：GitHub Actions 对 **Public 仓库终身免费、无上限**。本仓库用量每天 ~1 分钟 CPU，离收费线差着 98%。Public 仓库**不需要绑卡**。

## 这个仓库是干嘛的

- 电脑关机导致本地 cron 漏签（损失 $25/天）→ 把签到脚本搬到 GitHub Actions，云托管、永远在线。
- 每次运行：登录 airouter → 登出 → 重登（触发当日 $25）→ 读真余额（`quota ÷ 500000` 美元）→ 追加台账 `ledger.json` → 漏签检测 → 把台账 commit 回仓库（跨天持久化历史）。

## 文件

| 文件 | 作用 |
|---|---|
| `airouter_daily.py` | 签到主脚本（幂等，重复跑不重复加钱） |
| `.github/workflows/signin.yml` | 定时触发器（每天 UTC 00:00 = 北京 08:00）+ 手动触发 |
| `ledger.json` | 签到台账（脚本自动创建/更新，含历史 + 余额 + 漏签日期） |

## 部署（一次性，10 分钟）

**① 建仓库**
- GitHub → New repository → 名字随意 → **选 Public** → 不要勾 README/`.gitignore`（保持空仓库，便于上传）。

**② 填 2 个 Secrets**（凭据，绝不写进代码）
- 仓库 → **Settings → Secrets and variables → Actions → New repository secret**：
  - `AGENTROUTER_USER` = airouter 账号
  - `AGENTROUTER_PASS` = airouter 密码
- `AGENTROUTER_BASE` 不用建（脚本默认 `https://ps.air-outer.com`）。

**③ 上传 3 个文件**
- 仓库页面 → **Add file → Upload files**，拖入：
  - `airouter_daily.py`（根目录）
  - `ledger.json`（根目录，可选——没有会自动建）
  - `.github/workflows/signin.yml`（放进 `.github/workflows/` 子目录；本地已建好，直接拖）
- Commit 到 main。

**④ 手动验证一次**
- **Actions 标签 → `Airouter Daily Signin` → Run workflow → main**
- 日志应输出 `[agentrouter 2026-10-XX 08:00] 签到有效 | 余额 $XXXX`，且自动 commit 一条 `sign-in ...`。

**⑤ 验证自动 cron**
- 次日 08:00 看 Actions 是否自动跑 + commit 新 ledger；或手动再跑一次确认**幂等**（当天已签过不重复加 $25）。

## 怎么触发

| 方式 | 说明 |
|---|---|
| 自动 | 每天北京 00:30（UTC 17:30）cron 触发，早于本机 08:00 签到 |
| 手动 | Actions → `Airouter Daily Signin` → **Run workflow**（补签/测试用） |

## 漏签了怎么办

- `ledger.json` 有完整历史，脚本每次跑会检测**连续缺天**并打印 `漏签日期: ...`。
- 想补某天的签到：用**手动触发**跑一次即可（签到奖励按当日，补跑补的是"当天"而非历史缺天——历史缺天无法追溯补签，只能靠每天稳定跑避免再漏）。

## 怎么删

1. 仓库 → **Settings（底部红字）→ Delete this repository** → 输入仓库名确认删除。
2. 删前注意：
   - 本仓库删除后，airouter 签到**不再自动跑**，会重新漏签。
   - 若要保留历史台账，删前先下载 `ledger.json`（或把内容存进 `D:/1myfiles/yun_new/docs/prejects_memory/`）。
   - 若想彻底断联，删仓库后 airouter 账号本身不受影响（它只是不自动登录了）。

## 运维备注

- 脚本**无第三方依赖**（只用 Python 标准库 `urllib/json`），GitHub ubuntu-latest runner 自带 Python，无需装包。
- 余额真相源是 `/api/user/self` 的 `quota`，**不要用登录返回的 quota=0**（那是假值）。
- 单写者：本仓库由总指挥（@hermes）维护；改 `signin.yml`/`airouter_daily.py` 前确认 secrets 名一致。
- 台账 `ledger.json` 由 workflow 自动 commit（`contents: write` 权限），不要手动改它（会被下次运行覆盖合并）。

## 关联

- 本地原始 cron：`C:/Users/wen/AppData/Local/hermes/scripts/airouter_daily.py` + `cron/jobs.json` 的 `agentrouter-daily-login`。云跑通稳定 1-2 周后，可删本机 cron 作兜底。
- 模型域/额度台账：`D:/1myfiles/yun_new/docs/prejects_memory/`。


## 失败自动邮件（GitHub 原生，0 凭据）

`signin.yml` 的 `notifications: email` 字段让 workflow 失败时自动给仓库成员发邮件。
配合账号 Settings → Notifications 勾 "Email me when a workflow run fails"，双保险。

## 本机巡检双保险（airouter_signin_watch.py）

本机 cron 每日 09:00 跑 `airouter_signin_watch.py`：
- 拉 GitHub 仓库的 `ledger.json`（Public 免 token，走 `raw.githubusercontent.com`）
- 检查「今天是否已签到 + 余额是否 +$25」
- **正常 → 静默**（cron 不投递）
- **异常（缺行 / 余额未涨 / 拉取失败）→ 输出报警行**（cron 投递 bot-chat 提醒总指挥）

本机 cron 任务（`C:/Users/wen/AppData/Local/hermes/cron/jobs.json` 里的 `airouter_signin_watch`）：
```json
{
  "name": "airouter_signin_watch",
  "enabled": true,
  "schedule": {"kind": "cron", "expr": "0 9 * * *"},
  "payload": {
    "kind": "agent_turn",
    "message": "Run: C:/Users/wen/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe C:/Users/wen/AppData/Local/hermes/scripts/airouter_signin/airouter_signin_watch.py — 检查输出。若 OK 静默；若 ⚠️ 或 拉取失败，报警并附输出行。"
  },
  "delivery": {"mode": "announce", "error_target": "last"}
}
```

> **前提**：GitHub 仓库必须 **Public**（脚本免 token 拉取）。若将来改成 Private，需在脚本里加 GITHUB_TOKEN 或 PAT。

## 怎么删（完整）

1. **GitHub 端**：仓库 → Settings（底部红字）→ Delete this repository
2. **本机**：
   - 删 `C:/Users/wen/AppData/Local/hermes/scripts/airouter_signin/` 整个目录
   - 从 `C:/Users/wen/AppData/Local/hermes/cron/jobs.json` 删 `airouter_signin_watch` 任务
3. 删前注意：
   - 删掉后 airouter 签到不再自动跑，会重新漏签（$25/天）
   - 若要保留历史台账，删前先下载 `ledger.json`（或存进 `D:/1myfiles/yun_new/docs/prejects_memory/`）
