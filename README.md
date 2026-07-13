# Alwaysdata Auto Renew

通过模拟登录刷新 [alwaysdata](https://www.alwaysdata.com/) 免费账号活跃状态的自动化脚本，基于 GitHub Actions 定时运行。


## 使用方法

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret 名称 | 是否必需 | 说明 |
|---|---|---|
| `ACCOUNTS_JSON` | ✅ 必需 | 账号列表，JSON 数组，见下方格式 |
| `TG_BOT_TOKEN` | ⬜ 可选 | Telegram Bot Token，找 [@BotFather](https://t.me/BotFather) 申请 |
| `TG_CHAT_ID` | ⬜ 可选 | 接收通知的 Telegram 会话 ID |


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
