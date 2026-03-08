# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：server.py
# @Date   ：2026/03/08 12:00
# @Author ：leemysw
# 2026/03/08 12:00   Create - 独立回调服务器，支持 Agent 两步式认证
# =====================================================
"""
[INPUT]: 环境变量 FEISHU_APP_ID, FEISHU_APP_SECRET; CLI 参数 --state, --port, --lark
[OUTPUT]: 监听 OAuth 回调，用授权码换取 token 并保存到缓存
[POS]: auth 模块的独立回调服务器，可通过 python -m feishu_docx.auth.server 运行
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

独立进程运行的 OAuth 回调服务器。
凭证通过环境变量传递（安全，不暴露在 ps 中）。
"""

import argparse
import os
import sys

from feishu_docx.auth.oauth import OAuth2Authenticator, OAuthCallbackServer


def main():
    parser = argparse.ArgumentParser(description="Feishu OAuth callback server")
    parser.add_argument("--state", required=True, help="CSRF state token")
    parser.add_argument("--port", type=int, default=9527, help="Callback port")
    parser.add_argument("--lark", action="store_true", help="Use Lark (overseas)")
    args = parser.parse_args()

    # 从环境变量读取凭证
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print('{"error": "FEISHU_APP_ID and FEISHU_APP_SECRET must be set"}', file=sys.stderr)
        sys.exit(1)

    redirect_uri = os.environ.get("FEISHU_REDIRECT_URI")
    user_id = os.environ.get("FEISHU_USER_ID")

    # 启动回调服务器，等待一个请求（5分钟超时）
    server = OAuthCallbackServer(args.port)
    server.timeout = 300  # 5 minutes

    server.handle_request()

    if server.auth_error:
        print(f'{{"error": "{server.auth_error}"}}', file=sys.stderr)
        sys.exit(1)

    if not server.auth_code:
        print('{"error": "timeout"}', file=sys.stderr)
        sys.exit(1)

    # 验证 state
    if server.auth_state != args.state:
        print('{"error": "state_mismatch"}', file=sys.stderr)
        sys.exit(1)

    # 用授权码换取 token
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
    except Exception as e:
        print(f'{{"error": "{e}"}}', file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
