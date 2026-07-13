# Alwaysdata Auto Renew

通过模拟登录刷新 [alwaysdata](https://www.alwaysdata.com/) 免费账号活跃状态的自动化脚本，基于 GitHub Actions 定时运行。

## 特点

- **多账号**：一次运行可续期任意数量的账号
- **纯 HTTP 请求**：用 `requests` 模拟 Django 表单登录（CSRF token → POST 登录 → 校验 `sessionid`），不启动浏览器，更轻量、更稳定
- **账号隔离**：每个账号使用独立的 `requests.Session()`，互不影响
- **单次登录**：不对同一账号做失败重试，避免短时间内重复请求触发风控
- **随机延迟**：账号之间随机等待（默认 20-90 秒），避免固定节奏的请求指纹
- **不落地任何文件**：不截图、不写日志文件，运行结束即干净退出
- **日志脱敏**：控制台输出和 Telegram 通知里，账号统一显示为 `ab***@domain.com` 形式，不出现完整邮箱
- **Telegram 通知可选**：不配置就静默跳过，不影响主流程
- **Keepalive**：每次运行结束后提交一个 `.keepalive` 时间戳文件，防止仓库因 60 天无提交被 GitHub 自动暂停定时任务

## 文件说明

| 文件 | 作用 |
|---|---|
| `renew.py` | 主脚本 |
| `requirements.txt` | Python 依赖 |
| `.github/workflows/renew.yml` | GitHub Actions 工作流定义 |

## 使用方法

### 1. 放置文件

```
你的仓库/
├── renew.py
├── requirements.txt
└── .github/
    └── workflows/
        └── renew.yml
```

`renew.yml` 必须放在 `.github/workflows/` 目录下，GitHub 才能识别为工作流。

### 2. 配置 Secrets

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret 名称 | 是否必需 | 说明 |
|---|---|---|
| `ACCOUNTS_JSON` | ✅ 必需 | 账号列表，JSON 数组，见下方格式 |
| `TG_BOT_TOKEN` | ⬜ 可选 | Telegram Bot Token，找 [@BotFather](https://t.me/BotFather) 申请 |
| `TG_CHAT_ID` | ⬜ 可选 | 接收通知的 Telegram 会话 ID |

**务必放在 Secrets 里，不要放在 Variables 里** —— Variables 的值对仓库协作者是明文可见的。

`ACCOUNTS_JSON` 格式（多账号）：

```json
[
  {"username": "a@example.com", "password": "密码1"},
  {"username": "b@example.com", "password": "密码2"}
]
```

单账号也可以直接写一个对象：

```json
{"username": "a@example.com", "password": "密码1"}
```

**填写前建议先用 [jsonlint.com](https://jsonlint.com) 或本地 `python3 -m json.tool` 校验语法**，常见错误：用了中文引号、账号之间漏了逗号、末尾多了逗号、密码里有 `"` 或 `\` 没转义。

### 3. 确认权限

`renew.yml` 里已经声明了：

```yaml
permissions:
  contents: write
```

这是 keepalive 步骤往仓库 push 提交所必需的最小权限。如果仓库 Settings → Actions → General → Workflow permissions 里被设置成了 "Read repository contents permission"，需要改成允许写入，否则 keepalive 那步 push 会失败（不影响续期本身是否成功，只是 keepalive 提交不上去）。

### 4. 手动触发验证

改造完成后不用等到明天的定时任务，去仓库 **Actions → Alwaysdata Auto Renew → Run workflow** 手动跑一次，确认：
- 日志里每个账号都显示 `✅ 登录成功` / `✅ 面板访问成功`
- 如果配置了 Telegram，能收到一条汇总通知
- workflow 运行结束后仓库多了一次 `chore: keepalive YYYY-MM-DD` 提交

### 5. 定时策略

默认 `cron: '0 0 * * *'`，即每天 UTC 0 点（北京时间 8 点）运行一次。alwaysdata 免费账号通常只需要保持定期活跃即可，没必要设置成一天多次，请求频率越低越不容易被判定为异常行为。如需调整时间，直接改 `renew.yml` 里的 cron 表达式。

## 常见问题

**Q: 定时任务突然不跑了，Actions 页面也没有任何记录？**
GitHub 会在仓库连续 60 天没有 commit 时自动暂停该仓库的所有 scheduled workflow（`workflow_dispatch` 手动触发不受影响）。本项目已经内置 keepalive 机制解决这个问题——只要 workflow 本身每天成功跑过一次并 push 了 `.keepalive`，仓库就不会长期无提交。如果你把 keepalive 步骤删掉了，或者仓库有很长一段时间连一次成功运行都没有（比如账号全部到期作废），就可能触发这个暂停，需要手动进 Actions 页面重新启用一次。

**Q: `USERS_JSON`/`ACCOUNTS_JSON` 解析报 SyntaxError？**
说明 Secret 里填的不是合法 JSON，脚本会打印具体的解析错误位置但不会打印内容本身（避免密码进日志）。按上面"填写前建议先校验语法"那条排查。

**Q: 为什么不用浏览器自动化（Playwright/Puppeteer）？**
alwaysdata 登录页目前是普通的 Django 表单登录，没有 JS 反爬挑战，纯 HTTP 请求就能完成整个登录流程，比启动一个完整 Chrome 更快、更省资源、也更不容易在 CI 环境里出各种渲染/超时问题。如果未来该网站加上了 Cloudflare Turnstile 之类的验证码，纯 `requests` 会失效，届时需要换成浏览器自动化方案。

**Q: 截图/日志文件会不会被上传成 artifact 泄露账号信息？**
不会，本脚本完全不写文件到磁盘，也没有配置 `actions/upload-artifact` 步骤。

## 安全建议

- 仓库建议设为 **Private**，即使脚本本身不产生敏感文件，工作流日志（Actions 运行记录）默认所有仓库协作者可见。
- `ACCOUNTS_JSON` 中的密码只应存在于 GitHub Secrets 中，不要出现在任何 commit、issue、PR 描述里。
- 定期检查 alwaysdata 官方服务条款，确认自动化登录续期的方式是否仍被允许，条款变化可能影响账号安全。
