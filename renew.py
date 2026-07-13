#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alwaysdata 多账号自动续期脚本
- 纯 requests 模拟登录（CSRF token -> POST 登录 -> 校验 sessionid）
- 支持多账号（ACCOUNTS_JSON 环境变量，JSON 数组）
- 每个账号独立 Session，互不影响
- 单次登录尝试，不重试（避免短时间内反复请求同一账号触发风控）
- 账号之间随机延迟，规避固定节奏请求
- 不落地任何截图/调试文件
- Telegram 通知可选，运行结束后统一发送一条汇总消息
"""

import json
import os
import random
import sys
import time

import requests
from bs4 import BeautifulSoup

LOGIN_URL = "https://admin.alwaysdata.com/login/"
DASHBOARD_URL = "https://admin.alwaysdata.com/"
REQUEST_TIMEOUT = 20

# 账号之间的随机延迟范围（秒），可用环境变量覆盖
DELAY_MIN = int(os.getenv("DELAY_MIN_SECONDS", "20"))
DELAY_MAX = int(os.getenv("DELAY_MAX_SECONDS", "90"))


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────
def mask_username(username: str) -> str:
    """日志/通知里一律用脱敏后的用户名，不出现完整账号。"""
    value = str(username or "")
    if "@" not in value:
        return value[:1] + "*" if value else "?"
    name, _, domain = value.partition("@")
    masked_name = f"{name[:2]}***" if len(name) > 2 else f"{name[:1] or '*'}*"
    return f"{masked_name}@{domain}"


def build_session() -> requests.Session:
    """每个账号独立的 Session，天然隔离，不共享 cookie。"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": LOGIN_URL,
        "Origin": "https://admin.alwaysdata.com",
    })
    return session


def send_telegram(token: str, chat_id: str, text: str) -> None:
    """发送 Telegram 消息，失败时仅打印警告，不影响主流程/退出码。"""
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"⚠️  Telegram 通知发送失败（不影响主流程）: {e}")


# ──────────────────────────────────────────────
# 核心登录逻辑（单账号，单次尝试）
# ──────────────────────────────────────────────
def renew_one(username: str, password: str) -> bool:
    tag = mask_username(username)

    if not username or not password:
        print(f"[{tag}] ❌ 账号或密码为空，跳过")
        return False

    session = build_session()

    # Step 1: 获取登录页 + CSRF token
    print(f"[{tag}] 🔄 获取登录页 Token...")
    try:
        resp = session.get(LOGIN_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[{tag}] ❌ 无法访问登录页: {e}")
        return False

    soup = BeautifulSoup(resp.text, "html.parser")
    csrf_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
    if not csrf_input:
        print(f"[{tag}] ❌ 未找到 csrfmiddlewaretoken，页面结构可能已变更")
        return False
    csrf_token = csrf_input.get("value", "")

    # Step 2: 提交登录表单（单次，不重试）
    payload = {
        "csrfmiddlewaretoken": csrf_token,
        "login": username,
        "password": password,
        "alive": "on",
    }
    print(f"[{tag}] 🚀 提交登录请求...")
    try:
        login_resp = session.post(LOGIN_URL, data=payload, timeout=REQUEST_TIMEOUT)
        login_resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[{tag}] ❌ 登录请求失败: {e}")
        return False

    # Step 3: 校验 sessionid
    if "sessionid" not in session.cookies.get_dict():
        print(f"[{tag}] ❌ 登录失败：未获取到 sessionid（HTTP {login_resp.status_code}）")
        return False
    print(f"[{tag}] ✅ sessionid 已获取，登录成功")

    # Step 4: 访问后台确认活跃
    print(f"[{tag}] 🔍 访问管理面板确认账号活跃...")
    try:
        dash_resp = session.get(DASHBOARD_URL, timeout=REQUEST_TIMEOUT)
        if "login" in dash_resp.url:
            print(f"[{tag}] ❌ 会话无效：被重定向回登录页")
            return False
        print(f"[{tag}] ✅ 面板访问成功（HTTP {dash_resp.status_code}），续期完成")
    except requests.RequestException as e:
        # 已经拿到 sessionid，视为基本成功，这里仅警告
        print(f"[{tag}] ⚠️  访问面板网络错误（不影响续期结果）: {e}")

    return True


# ──────────────────────────────────────────────
# 入口：多账号循环
# ──────────────────────────────────────────────
def load_accounts() -> list:
    raw = os.getenv("ACCOUNTS_JSON", "").strip()
    if not raw:
        print("❌ 未配置 ACCOUNTS_JSON 环境变量")
        sys.exit(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # 不打印 raw 内容，避免把明文密码写进日志
        print(f"❌ 解析 ACCOUNTS_JSON 失败：{e}")
        sys.exit(1)

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        print("❌ ACCOUNTS_JSON 格式应为账号对象数组，例如 "
              '[{"username":"a@x.com","password":"xxx"}]')
        sys.exit(1)
    return data


def main():
    accounts = load_accounts()
    tg_token = os.getenv("TG_BOT_TOKEN", "").strip()
    tg_chat_id = os.getenv("TG_CHAT_ID", "").strip()

    results = []  # [(masked_username, bool), ...]
    total = len(accounts)

    for idx, account in enumerate(accounts):
        username = str(account.get("username", "")).strip()
        password = str(account.get("password", "")).strip()

        # 账号之间随机延迟，规避固定节奏的请求指纹；第一个账号也延迟一下，
        # 避免每天在 cron 触发后的同一秒发出第一个请求。
        delay = random.randint(DELAY_MIN, DELAY_MAX)
        print(f"⏳ 等待 {delay} 秒后处理第 {idx + 1}/{total} 个账号...")
        time.sleep(delay)

        ok = renew_one(username, password)
        results.append((mask_username(username), ok))

    success = sum(1 for _, ok in results if ok)
    print(f"完成: {success}/{total}")

    lines = [f"{'✅' if ok else '❌'} {name}" for name, ok in results]
    summary = (
        f"<b>Alwaysdata 续期结果 {success}/{total}</b>\n" + "\n".join(lines)
    )
    send_telegram(tg_token, tg_chat_id, summary)

    if success != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
