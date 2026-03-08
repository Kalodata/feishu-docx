# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：common.py
# @Date   ：2026/02/01 19:15
# @Author ：leemysw
# 2026/02/01 19:15   Create - 从 main.py 拆分
# 2026/03/09         Add require_auth helper
# =====================================================
"""
[INPUT]: 依赖 typer, feishu_docx.utils.config, feishu_docx.utils.console
[OUTPUT]: 对外提供 get_credentials, normalize_folder_token, require_auth, console
[POS]: cli 模块的共享工具函数
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import os
import re
from typing import Optional
from urllib.parse import urlparse

from feishu_docx.utils.config import AppConfig
from feishu_docx.utils.console import get_console

console = get_console()


def get_credentials(
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        auth_mode: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        user_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], str, Optional[str], Optional[str]]:
    """
    获取凭证（优先级：命令行参数 > 环境变量 > 配置文件）

    Args:
        app_id: 命令行传入的 App ID
        app_secret: 命令行传入的 App Secret
        auth_mode: 命令行传入的认证模式 (tenant/oauth)
        redirect_uri: 命令行传入的 OAuth 回调地址
        user_id: 命令行传入的用户标识

    Returns:
        (app_id, app_secret, auth_mode, redirect_uri, user_id)
        - auth_mode: "tenant" 使用 tenant_access_token，"oauth" 使用 user_access_token
        - redirect_uri: OAuth 回调地址，None 时使用默认值
        - user_id: 用户标识，用于隔离 OAuth token 缓存
    """
    # 加载配置文件作为 fallback
    config = AppConfig.load()

    # ========================================
    # 1. 确定 app_id (命令行 > 环境变量 > 配置)
    # ========================================
    final_app_id = (
        app_id
        or os.getenv("FEISHU_APP_ID")
        or config.app_id
    )

    # ========================================
    # 2. 确定 app_secret (命令行 > 环境变量 > 配置)
    # ========================================
    final_app_secret = (
        app_secret
        or os.getenv("FEISHU_APP_SECRET")
        or config.app_secret
    )

    # ========================================
    # 3. 确定 auth_mode (命令行 > 环境变量 > 配置 > 默认 tenant)
    # ========================================
    final_auth_mode = (
        auth_mode
        or os.getenv("FEISHU_AUTH_MODE")
        or config.auth_mode
        or "tenant"
    )

    # 验证 auth_mode 值
    if final_auth_mode not in ("tenant", "oauth"):
        final_auth_mode = "tenant"

    # ========================================
    # 4. 确定 redirect_uri (命令行 > 环境变量 > 配置 > None)
    # ========================================
    final_redirect_uri = (
        redirect_uri
        or os.getenv("FEISHU_REDIRECT_URI")
        or config.redirect_uri
    )

    # ========================================
    # 5. 确定 user_id (命令行 > 环境变量)
    # ========================================
    final_user_id = user_id or os.getenv("FEISHU_USER_ID")

    # 检查凭证完整性
    if final_app_id and final_app_secret:
        return final_app_id, final_app_secret, final_auth_mode, final_redirect_uri, final_user_id

    return None, None, final_auth_mode, final_redirect_uri, final_user_id


def require_auth(
        user_id: Optional[str],
        is_lark: bool = False,
        redirect_uri: Optional[str] = None,
):
    """
    检查用户 OAuth token 是否有效，无效则报错并生成 auth-start 命令。

    仅当 user_id 非空时检查（user_id 模式 = Agent 模式）。
    """
    if not user_id:
        return

    from feishu_docx.auth.oauth import OAuth2Authenticator
    authenticator = OAuth2Authenticator(user_id=user_id, redirect_uri=redirect_uri)
    if authenticator._load_from_cache() and not authenticator._token_info.is_expired():
        return

    # 构建 auth-start 命令
    cmd = f"feishu-docx auth-start --user-id {user_id}"
    if is_lark:
        cmd += " --lark"
    if redirect_uri:
        cmd += f" --redirect-uri {redirect_uri}"

    console.print(
        f"[red]❌ 用户 [bold]{user_id}[/bold] 未授权或 token 已过期[/red]\n\n"
        f"请先运行授权命令：\n"
        f"  [cyan]{cmd}[/cyan]"
    )
    import typer
    raise typer.Exit(1)


def normalize_folder_token(folder: Optional[str]) -> Optional[str]:
    """从 URL 或 token 提取 folder token"""
    if not folder:
        return None
    if re.match(r"^[A-Za-z0-9]+$", folder):
        return folder
    try:
        parsed = urlparse(folder)
        if not parsed.path:
            return folder
        match = re.search(r"/drive/folder/([A-Za-z0-9]+)", parsed.path)
        if match:
            return match.group(1)
    except Exception:
        return folder
    return folder
