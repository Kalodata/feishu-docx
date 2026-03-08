# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：server.py
# @Date   ：2026/03/08 12:00
# @Author ：leemysw
# 2026/03/08 12:00   Create - 独立回调服务器，支持 Agent 两步式认证
# =====================================================
"""
[INPUT]: 环境变量 FEISHU_APP_ID, FEISHU_APP_SECRET; CLI 参数 --state, --port, --host, --lark
[OUTPUT]: 监听 OAuth 回调，用授权码换取 token 并保存到缓存；关键步骤日志输出到 stderr
[POS]: auth 模块的独立回调服务器，可通过 python -m feishu_docx.auth.server 运行
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

独立进程运行的 OAuth 回调服务器。
凭证通过环境变量传递（安全，不暴露在 ps 中）。
"""

import argparse
import os
import sys

from feishu_docx.auth.oauth import OAuth2Authenticator, OAuthCallbackServer


def log(msg: str):
    """写日志到 stderr"""
    print(f"[auth-server] {msg}", file=sys.stderr, flush=True)


def main():
    parser = argparse.ArgumentParser(description="Feishu OAuth callback server")
    parser.add_argument("--state", required=True, help="CSRF state token")
    parser.add_argument("--port", type=int, default=9527, help="Callback port")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--lark", action="store_true", help="Use Lark (overseas)")
    args = parser.parse_args()

    # 从环境变量读取凭证
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        log("ERROR: FEISHU_APP_ID and FEISHU_APP_SECRET must be set")
        sys.exit(1)

    redirect_uri = os.environ.get("FEISHU_REDIRECT_URI")
    user_id = os.environ.get("FEISHU_USER_ID")

    # 启动回调服务器，等待一个请求（5分钟超时）
    log(f"Starting callback server on {args.host}:{args.port}")
    server = OAuthCallbackServer(args.port, host=args.host)
    server.timeout = 300  # 5 minutes

    log("Waiting for OAuth callback (timeout=300s)...")
    server.handle_request()

    if server.auth_error:
        log(f"Auth error: {server.auth_error}")
        sys.exit(1)

    if not server.auth_code:
        log("Timeout: no callback received")
        sys.exit(1)

    # 验证 state
    if server.auth_state != args.state:
        log(f"State mismatch: expected={args.state}, got={server.auth_state}")
        sys.exit(1)
    log("State verified OK")

    # 用授权码换取 token
    log("Exchanging auth code for token...")
    authenticator = OAuth2Authenticator(
        app_id=app_id,
        app_secret=app_secret,
        redirect_port=args.port,
        is_lark=args.lark,
        redirect_uri=redirect_uri,
        user_id=user_id,
    )
    try:
        authenticator._exchange_token(server.auth_code)
        log("Token exchange successful")
    except Exception as e:
        log(f"Token exchange failed: {e}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
