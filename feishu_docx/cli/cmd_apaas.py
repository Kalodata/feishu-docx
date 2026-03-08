# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：cmd_apaas.py
# @Date   ：2026/02/01 19:15
# @Author ：leemysw
# 2026/02/01 19:15   Create - 从 main.py 拆分
# =====================================================
"""
[INPUT]: 依赖 typer, feishu_docx.core.exporter
[OUTPUT]: 对外提供 export_workspace_schema 命令
[POS]: cli 模块的 APaaS 相关命令
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

from feishu_docx.core.exporter import FeishuExporter
from .common import console, get_credentials


# ==============================================================================
# export-workspace-schema 命令 - 导出数据库结构
# ==============================================================================


def export_workspace_schema(
        workspace_id: str = typer.Argument(..., help="工作空间 ID"),
        output: Path = typer.Option(
            Path("./database_schema.md"),
            "-o",
            "--output",
            help="输出文件路径",
        ),
        token: Optional[str] = typer.Option(
            None,
            "-t",
            "--token",
            envvar="FEISHU_ACCESS_TOKEN",
            help="用户访问凭证",
        ),
        app_id: Optional[str] = typer.Option(None, "--app-id", help="飞书应用 App ID"),
        app_secret: Optional[str] = typer.Option(None, "--app-secret", help="飞书应用 App Secret"),
        auth_mode: Optional[str] = typer.Option(None, "--auth-mode", help="认证模式: tenant / oauth"),
        lark: bool = typer.Option(False, "--lark", help="使用 Lark (海外版)"),
        user_id: Optional[str] = typer.Option(None, "--user-id", help="用户标识，使用指定用户的 OAuth token"),
):
    """
    [green]▶[/] 导出数据库结构为 Markdown

    示例:

        # 导出工作空间数据库结构\\\\n
        feishu-docx export-workspace-schema <workspace_id>

        # 指定输出文件\\\\n
        feishu-docx export-workspace-schema <workspace_id> -o schema.md
    """
    try:
        # 获取凭证
        if token:
            exporter = FeishuExporter.from_token(token)
            access_token = token
        else:
            final_app_id, final_app_secret, final_auth_mode, final_redirect_uri, final_user_id = get_credentials(app_id, app_secret, auth_mode, user_id=user_id)
            if not final_app_id or not final_app_secret:
                console.print("[red]❌ 需要提供凭证[/red]")
                raise typer.Exit(1)
            exporter = FeishuExporter(app_id=final_app_id, app_secret=final_app_secret, is_lark=lark, auth_mode=final_auth_mode, redirect_uri=final_redirect_uri, user_id=final_user_id)
            access_token = exporter.get_access_token()

        console.print(f"[blue]> 工作空间 ID:[/blue] {workspace_id}")
        console.print("[yellow]> 正在获取数据表列表...[/yellow]")

        # 获取所有数据表
        tables = exporter.sdk.apaas.get_all_workspace_tables(
            workspace_id=workspace_id,
            access_token=access_token,
        )

        if not tables:
            console.print("[yellow]⚠ 未找到数据表[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]✓ 找到 {len(tables)} 个数据表[/green]")

        # 生成 Markdown
        markdown_lines = [
            "# 工作空间数据库结构",
            "",
            f"**工作空间 ID**: `{workspace_id}`",
            f"**数据表数量**: {len(tables)}",
            "",
        ]

        for table in tables:
            table_name = table.get("name", "")
            description = table.get("description", "")
            columns = table.get("columns", [])

            markdown_lines.extend([
                f"## 📋 {table_name}",
                "",
            ])

            if description:
                markdown_lines.extend([f"> {description}", ""])

            markdown_lines.extend([
                "| 列名 | 类型 | 主键 | 唯一 | 自增 | 数组 | 允许空 | 默认值 | 描述 |",
                "|------|------|------|------|------|------|--------|--------|------|",
            ])

            for col in columns:
                row = (
                    f"| {col.get('name', '')} "
                    f"| {col.get('data_type', '')} "
                    f"| {'✓' if col.get('is_primary_key') else ''} "
                    f"| {'✓' if col.get('is_unique') else ''} "
                    f"| {'✓' if col.get('is_auto_increment') else ''} "
                    f"| {'✓' if col.get('is_array') else ''} "
                    f"| {'✓' if col.get('is_allow_null') else ''} "
                    f"| {col.get('default_value', '')} "
                    f"| {col.get('description', '')} |"
                )
                markdown_lines.append(row)

            markdown_lines.append("")

        # 保存文件
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(markdown_lines), encoding="utf-8")

        console.print(Panel(f"✅ 数据库结构已导出: [green]{output}[/green]", border_style="green"))

    except Exception as e:
        console.print(f"[red]❌ 导出失败: {e}[/red]")
        raise typer.Exit(1)
