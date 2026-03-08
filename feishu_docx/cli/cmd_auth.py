# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：cmd_auth.py
# @Date   ：2026/02/01 19:15
# @Author ：leemysw
# 2026/02/01 19:15   Create - 从 main.py 拆分
# 2026/03/08 12:00   Add auth-start, auth-check for Agent two-step flow
# 2026/03/08         auth-start: add logging + server binds 0.0.0.0
# =====================================================
"""
[INPUT]: 依赖 typer, feishu_docx.auth.oauth
[OUTPUT]: 对外提供 auth, auth_start, auth_check 命令
[POS]: cli 模块的认证命令
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

from feishu_docx.auth.oauth import OAuth2Authenticator
from .common import console, get_credentials


# ==============================================================================
# auth 命令
# ==============================================================================


def auth(
        app_id: Optional[str] = typer.Option(
            None,
            "--app-id",
            help="飞书应用 App ID（覆盖配置文件）",
        ),
        app_secret: Optional[str] = typer.Option(
            None,
            "--app-secret",
            help="飞书应用 App Secret（覆盖配置文件）",
        ),
        auth_mode: Optional[str] = typer.Option(
            None,
            "--auth-mode",
            help="认证模式: tenant / oauth（覆盖配置文件）",
        ),
        lark: bool = typer.Option(
            False,
            "--lark",
            help="使用 Lark (海外版)",
        ),
        redirect_uri: Optional[str] = typer.Option(
            None,
            "--redirect-uri",
            help="自定义 OAuth 回调地址（覆盖配置文件）",
        ),
        user_id: Optional[str] = typer.Option(
            None,
            "--user-id",
            help="用户标识，token 按用户隔离存储",
        ),
):
    """
    [yellow]❁[/] 获取授权，获取并缓存 Token

    首次使用前运行此命令进行授权：

        # 使用已配置的凭证（推荐，需先运行 feishu-docx config set）
        feishu-docx auth

        # 或指定凭证
        feishu-docx auth --app-id xxx --app-secret xxx

    授权成功后，Token 将被缓存，后续导出无需再次授权。
    """
    try:
        # 获取凭证
        final_app_id, final_app_secret, final_auth_mode, final_redirect_uri, final_user_id = get_credentials(app_id, app_secret, auth_mode, redirect_uri, user_id)

        if not final_app_id or not final_app_secret:
            console.print(
                "[red]❌ 需要提供 OAuth 凭证[/red]\n\n"
                "方式一：先配置凭证（推荐）\n"
                "  [cyan]feishu-docx config set --app-id xxx --app-secret xxx[/cyan]\n\n"
                "方式二：命令行传入\n"
                "  [cyan]feishu-docx auth --app-id xxx --app-secret xxx[/cyan]"
            )
            raise typer.Exit(1)

        authenticator = OAuth2Authenticator(
            app_id=final_app_id,
            app_secret=final_app_secret,
            is_lark=lark,
            redirect_uri=final_redirect_uri,
            user_id=final_user_id,
        )

        console.print("[yellow]>[/yellow] 正在进行 OAuth 授权...")
        token = authenticator.authenticate()

        console.print(Panel(
            f"✅ 授权成功！\n\n"
            f"Token 已缓存至: [cyan]{authenticator.cache_file}[/cyan]\n\n"
            f"后续使用 [green]feishu-docx export[/green] 命令将自动使用缓存的 Token。",
            title="授权成功",
            border_style="green",
        ))

    except Exception as e:
        console.print(f"[red]❌ 授权失败: {e}[/red]")
        raise typer.Exit(1)


# ==============================================================================
# auth-start 命令（Agent 友好：非阻塞，返回 JSON）
# ==============================================================================


def auth_start(
        lark: bool = typer.Option(
            False,
            "--lark",
            help="使用 Lark (海外版)",
        ),
        redirect_uri: Optional[str] = typer.Option(
            None,
            "--redirect-uri",
            help="自定义 OAuth 回调地址（覆盖配置文件）",
        ),
        user_id: Optional[str] = typer.Option(
            None,
            "--user-id",
            help="用户标识，token 按用户隔离存储",
        ),
):
    """
    [yellow]❁[/] 启动 OAuth 授权（Agent 模式）

    非阻塞式授权，返回 JSON 包含授权 URL 和后台进程 PID：

        feishu-docx auth-start --user-id xxx

    输出: {"url": "https://...", "pid": 12345}

    配合 auth-check 使用，适合 AI Agent 调用。
    """
    try:
        # 获取凭证
        print("[auth-start] Checking credentials...", file=sys.stderr, flush=True)
        final_app_id, final_app_secret, _, final_redirect_uri, final_user_id = get_credentials(
            None, None, None, redirect_uri, user_id,
        )

        if not final_app_id or not final_app_secret:
            print("[auth-start] Credentials missing", file=sys.stderr, flush=True)
            print(json.dumps({"error": "credentials_missing"}))
            raise typer.Exit(1)

        # 先检查缓存 token
        authenticator = OAuth2Authenticator(
            app_id=final_app_id,
            app_secret=final_app_secret,
            is_lark=lark,
            redirect_uri=final_redirect_uri,
            user_id=final_user_id,
        )
        if authenticator._load_from_cache() and not authenticator._token_info.is_expired():
            print("[auth-start] Cached token still valid", file=sys.stderr, flush=True)
            print(json.dumps({"status": "authenticated"}))
            return

        # 生成 state，构建 auth URL
        state = secrets.token_urlsafe(16)
        auth_url = authenticator.build_auth_url(state)
        print(f"[auth-start] Auth URL generated, state={state[:8]}...", file=sys.stderr, flush=True)

        # 日志文件
        log_dir = Path.home() / ".feishu-docx"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "auth-server.log"

        # 通过环境变量传递凭证，启动后台回调服务器
        env = os.environ.copy()
        env["FEISHU_APP_ID"] = final_app_id
        env["FEISHU_APP_SECRET"] = final_app_secret
        if final_redirect_uri:
            env["FEISHU_REDIRECT_URI"] = final_redirect_uri
        if final_user_id:
            env["FEISHU_USER_ID"] = final_user_id

        cmd = [
            sys.executable, "-m", "feishu_docx.auth.server",
            "--state", state,
            "--port", str(authenticator.redirect_port),
            "--host", "0.0.0.0",
        ]
        if lark:
            cmd.append("--lark")

        log_fh = open(log_file, "w")
        proc = subprocess.Popen(
            cmd,
            env=env,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=log_fh,
        )
        print(f"[auth-start] Server process started, pid={proc.pid}", file=sys.stderr, flush=True)

        print(json.dumps({"url": auth_url, "pid": proc.pid, "log": str(log_file)}))

    except typer.Exit:
        raise
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        raise typer.Exit(1)


# ==============================================================================
# auth-check 命令（Agent 友好：检查 token 状态）
# ==============================================================================


def auth_check(
        user_id: Optional[str] = typer.Option(
            None,
            "--user-id",
            help="用户标识，token 按用户隔离存储",
        ),
):
    """
    [yellow]❁[/] 检查 OAuth 授权状态（Agent 模式）

    检查 token 是否已获取：

        feishu-docx auth-check --user-id xxx

    输出: {"authenticated": true} 或 {"authenticated": false}
    """
    try:
        _, _, _, _, final_user_id = get_credentials(None, None, None, None, user_id)

        authenticator = OAuth2Authenticator(user_id=final_user_id)
        authenticated = authenticator._load_from_cache() and not authenticator._token_info.is_expired()

        print(json.dumps({"authenticated": authenticated}))

    except Exception as e:
        print(json.dumps({"authenticated": False, "error": str(e)}))
        raise typer.Exit(1)
