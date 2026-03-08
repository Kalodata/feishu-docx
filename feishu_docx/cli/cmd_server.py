# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：cmd_server.py
# @Date   ：2026/03/08 14:00
# @Author ：leemysw
# 2026/03/08 14:00   Create - OAuth 回调服务器管理命令
# =====================================================
"""
[INPUT]: 依赖 typer, feishu_docx.auth.server
[OUTPUT]: 对外提供 server_start, server_stop, server_status 命令
[POS]: cli 模块的服务器管理命令
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import typer

from feishu_docx.auth.server import (
    PID_FILE,
    is_server_running,
    read_pid_file,
    remove_pid_file,
)
from .common import console


# ==============================================================================
# server start 命令
# ==============================================================================

def server_start(
        port: int = typer.Option(9527, "--port", "-p", help="回调服务器端口"),
        host: str = typer.Option("0.0.0.0", "--host", help="绑定地址"),
        foreground: bool = typer.Option(False, "--foreground", "-f", help="前台运行（不后台化）"),
):
    """
    启动 OAuth 回调服务器

    服务器将持久运行，处理所有 OAuth 回调请求。

        feishu-docx server start
        feishu-docx server start --port 9527
        feishu-docx server start --foreground  # 前台运行
    """
    # 检查是否已在运行
    running, info = is_server_running()
    if running:
        console.print(
            f"[yellow]服务器已在运行[/yellow] (PID={info['pid']}, port={info['port']})"
        )
        return

    if foreground:
        # 前台运行：直接 exec
        console.print(f"[green]>[/green] 前台启动服务器 {host}:{port}")
        from feishu_docx.auth.server import main as server_main
        sys.argv = ["server", "--port", str(port), "--host", host]
        server_main()
        return

    # 后台运行：spawn 子进程
    log_dir = Path.home() / ".feishu-docx"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "auth-server.log"

    cmd = [
        sys.executable, "-m", "feishu_docx.auth.server",
        "--port", str(port),
        "--host", host,
    ]

    log_fh = open(log_file, "w")
    proc = subprocess.Popen(
        cmd,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=log_fh,
    )

    # 等待启动
    time.sleep(0.5)
    if proc.poll() is not None:
        log_fh.close()
        log_content = log_file.read_text(encoding="utf-8").strip()
        console.print(f"[red]服务器启动失败[/red]: {log_content}")
        raise typer.Exit(1)

    # 健康检查
    import urllib.request
    health_ok = False
    for _ in range(5):
        try:
            check_host = "127.0.0.1" if host == "0.0.0.0" else host
            req = urllib.request.urlopen(
                f"http://{check_host}:{port}/health", timeout=2
            )
            if req.status == 200:
                health_ok = True
                break
        except Exception:
            time.sleep(0.3)

    if not health_ok:
        console.print("[yellow]服务器已启动但健康检查未通过，可能需要等待[/yellow]")

    console.print(
        f"[green]服务器已启动[/green] (PID={proc.pid}, port={port})\n"
        f"日志文件: [dim]{log_file}[/dim]"
    )


# ==============================================================================
# server stop 命令
# ==============================================================================

def server_stop():
    """
    停止 OAuth 回调服务器

        feishu-docx server stop
    """
    running, info = is_server_running()
    if not running:
        console.print("[yellow]服务器未在运行[/yellow]")
        # 清理残留 PID 文件
        if PID_FILE.exists():
            remove_pid_file()
        return

    pid = info["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
        # 等待进程退出
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.3)
            except (OSError, ProcessLookupError):
                break
        console.print(f"[green]服务器已停止[/green] (PID={pid})")
    except (OSError, ProcessLookupError):
        console.print(f"[yellow]进程 {pid} 已不存在[/yellow]")

    remove_pid_file()


# ==============================================================================
# server status 命令
# ==============================================================================

def server_status():
    """
    查看 OAuth 回调服务器状态

        feishu-docx server status
    """
    running, info = is_server_running()
    if running:
        console.print(
            f"[green]Running[/green]  PID={info['pid']}  port={info['port']}  "
            f"started={info.get('started_at', 'unknown')}"
        )
    else:
        console.print("[dim]Stopped[/dim]  服务器未在运行")
