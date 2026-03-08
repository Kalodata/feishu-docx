# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：server.py
# @Date   ：2026/03/08 12:00
# @Author ：leemysw
# 2026/03/08 12:00   Create - 独立回调服务器，支持 Agent 两步式认证
# 2026/03/08         Rewrite - 持久化回调服务，通过 pending 文件注册 state
# =====================================================
"""
[INPUT]: CLI 参数 --port, --host; pending/{state}.json 文件; config/env 凭证
[OUTPUT]: 持久监听 OAuth 回调，根据 state 查找 user_id，换 token 写入对应文件
[POS]: auth 模块的持久回调服务器，通过 server start/stop 管理
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

持久进程运行的 OAuth 回调服务器。
凭证通过 AppConfig / 环境变量获取（不再依赖父进程传递）。
状态注册通过文件系统 ~/.feishu-docx/pending/{state}.json 完成。
"""

import argparse
import json
import os
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from feishu_docx.auth.oauth import OAuth2Authenticator
from feishu_docx.auth.templates import SUCCESS_HTML, get_error_html
from feishu_docx.utils.config import AppConfig

# ==============================================================================
# 路径常量
# ==============================================================================
BASE_DIR = Path.home() / ".feishu-docx"
PID_FILE = BASE_DIR / "auth-server.pid"
PENDING_DIR = BASE_DIR / "pending"


def log(msg: str):
    """写日志到 stderr"""
    print(f"[auth-server] {msg}", file=sys.stderr, flush=True)


# ==============================================================================
# PID 文件管理
# ==============================================================================

def write_pid_file(pid: int, port: int):
    """写入 PID 文件"""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps({
        "pid": pid,
        "port": port,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }))


def read_pid_file() -> dict | None:
    """读取 PID 文件，返回 None 如果不存在"""
    if not PID_FILE.exists():
        return None
    try:
        return json.loads(PID_FILE.read_text())
    except Exception:
        return None


def remove_pid_file():
    """删除 PID 文件"""
    if PID_FILE.exists():
        PID_FILE.unlink(missing_ok=True)


def is_server_running() -> tuple[bool, dict | None]:
    """检查服务器是否在运行：读 PID 文件 + os.kill(pid, 0) 检查进程"""
    info = read_pid_file()
    if not info:
        return False, None
    pid = info.get("pid")
    if not pid:
        return False, None
    try:
        os.kill(pid, 0)
        return True, info
    except (OSError, ProcessLookupError):
        # 进程不存在，清理残留 PID 文件
        remove_pid_file()
        return False, None


# ==============================================================================
# 凭证获取（不依赖 cli 模块）
# ==============================================================================

def _get_credentials() -> tuple[str | None, str | None, str | None]:
    """从 config/env 获取 app_id, app_secret, redirect_uri"""
    config = AppConfig.load()
    app_id = os.getenv("FEISHU_APP_ID") or config.app_id
    app_secret = os.getenv("FEISHU_APP_SECRET") or config.app_secret
    redirect_uri = os.getenv("FEISHU_REDIRECT_URI") or config.redirect_uri
    return app_id, app_secret, redirect_uri


# ==============================================================================
# HTTP Handler
# ==============================================================================

class CallbackHandler(BaseHTTPRequestHandler):
    """处理 OAuth 回调的持久 HTTP Handler"""

    # 错误代码映射
    ERROR_MESSAGES = {
        "access_denied": "您拒绝了授权请求",
        "invalid_request": "请求参数无效",
        "unauthorized_client": "应用未授权",
        "unsupported_response_type": "不支持的响应类型",
        "invalid_scope": "请求的权限无效",
        "server_error": "服务器内部错误",
    }

    def log_message(self, format, *args):
        """输出请求日志到 stderr"""
        log(format % args)

    def do_GET(self):
        """处理 GET 请求"""
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._handle_health()
            return

        # OAuth 回调处理（根路径）
        if parsed.path == "/":
            self._handle_callback(parsed)
            return

        self.send_error(404, "Not Found")

    def _handle_health(self):
        """GET /health — 健康检查"""
        body = json.dumps({"status": "ok"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_callback(self, parsed):
        """GET / — OAuth 回调处理"""
        query = parse_qs(parsed.query)

        if "code" not in query:
            error = query.get("error", ["unknown"])[0]
            error_desc = self.ERROR_MESSAGES.get(error, f"未知错误: {error}")
            html = get_error_html(error, error_desc)
            self._send_html(400, html)
            return

        code = query["code"][0]
        state = query.get("state", [None])[0]

        if not state:
            log("Callback missing state parameter")
            self._send_html(400, get_error_html("missing_state", "缺少 state 参数"))
            return

        # 读取 pending/{state}.json
        pending_file = PENDING_DIR / f"{state}.json"
        if not pending_file.exists():
            log(f"No pending file for state={state[:8]}...")
            self._send_html(400, get_error_html("invalid_state", "无效的 state，可能已过期"))
            return

        try:
            pending_data = json.loads(pending_file.read_text())
        except Exception as e:
            log(f"Failed to read pending file: {e}")
            self._send_html(500, get_error_html("internal_error", "读取状态文件失败"))
            return

        user_id = pending_data.get("user_id")
        is_lark = pending_data.get("is_lark", False)

        # 获取凭证
        app_id, app_secret, redirect_uri = _get_credentials()
        if not app_id or not app_secret:
            log("Credentials missing, cannot exchange token")
            self._send_html(500, get_error_html("credentials_missing", "服务器缺少应用凭证"))
            return

        # 换 token
        log(f"Exchanging token for state={state[:8]}..., user_id={user_id}")
        try:
            authenticator = OAuth2Authenticator(
                app_id=app_id,
                app_secret=app_secret,
                redirect_port=self.server.server_port,
                is_lark=is_lark,
                redirect_uri=redirect_uri,
                user_id=user_id,
            )
            authenticator._exchange_token(code)
            log(f"Token exchange successful for user_id={user_id}")
        except Exception as e:
            log(f"Token exchange failed: {e}")
            self._send_html(500, get_error_html("token_exchange_failed", f"Token 换取失败: {e}"))
            return

        # 删除 pending 文件
        try:
            pending_file.unlink()
        except Exception:
            pass

        # 返回成功页面
        self._send_html(200, SUCCESS_HTML)

    def _send_html(self, status: int, html: str):
        """发送 HTML 响应"""
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ==============================================================================
# HTTP Server
# ==============================================================================

class CallbackServer(HTTPServer):
    """持久 OAuth 回调服务器"""
    allow_reuse_address = True


# ==============================================================================
# 入口
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Feishu OAuth persistent callback server")
    parser.add_argument("--port", type=int, default=9527, help="Callback port")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    args = parser.parse_args()

    # 确保 pending 目录存在
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    # 写 PID 文件
    write_pid_file(os.getpid(), args.port)

    # 信号处理：优雅退出
    def shutdown_handler(signum, frame):
        log("Received shutdown signal, exiting...")
        remove_pid_file()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    # 启动服务器
    server = CallbackServer((args.host, args.port), CallbackHandler)
    log(f"Persistent callback server started on {args.host}:{args.port}")
    log(f"PID={os.getpid()}, PID file={PID_FILE}")
    log("Waiting for OAuth callbacks...")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        remove_pid_file()
        log("Server stopped")


if __name__ == "__main__":
    main()
