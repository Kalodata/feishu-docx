---
name: feishu-docx
description: Export Feishu/Lark cloud documents to Markdown. Supports docx, sheets, bitable, wiki, and batch wiki space export. Use this skill when you need to read, analyze, write, or reference content from Feishu knowledge base.
---

# Feishu Docx Exporter

Export Feishu/Lark cloud documents to Markdown format for AI analysis.

> **All commands require `--user-id <USER_ID>`** to specify which user's token to use.

## Authentication (auth-first)

**Before any command**, check auth status first:

```bash
# Step 1: Check if already authenticated
feishu-docx auth-check --user-id <USER_ID>
# Output: {"authenticated": true}  → proceed to your command
# Output: {"authenticated": false} → go to Step 2
```

If not authenticated, run the **two-step auth flow** (Agent-friendly, non-blocking):

```bash
# Step 2: Start OAuth — returns JSON with URL and background server PID
feishu-docx auth-start --user-id <USER_ID>
# Output: {"url": "https://accounts.feishu.cn/...", "pid": 12345}

# Step 3: Present the URL to the user and ask them to authorize in browser

# Step 4: Poll until authorization completes
feishu-docx auth-check --user-id <USER_ID>
# Output: {"authenticated": true}  → proceed to your command

# Step 5: Clean up the background server
kill <pid>
```

**Alternative (interactive):** `feishu-docx auth --user-id <USER_ID>` runs the full OAuth flow in a single blocking command (opens browser, waits up to 2 minutes).

The token caches to `~/.feishu-docx/tokens/<USER_ID>.json` and auto-refreshes. Re-auth is only needed if the refresh token expires.

## Export Documents

```bash
feishu-docx export "<FEISHU_URL>" -o ./output --user-id <USER_ID>
```

The exported Markdown file will be saved with the document's title as filename.

### Supported Document Types

- **docx**: Feishu cloud documents → Markdown with images
- **sheet**: Spreadsheets → Markdown tables
- **bitable**: Multidimensional tables → Markdown tables
- **wiki**: Knowledge base nodes → Auto-resolved and exported

## Command Reference

| Command | Description |
|---------|-------------|
| `feishu-docx auth-start --user-id <USER_ID>` | Start OAuth (non-blocking, returns JSON) |
| `feishu-docx auth-check --user-id <USER_ID>` | Check if OAuth token exists |
| `feishu-docx export <URL> --user-id <USER_ID>` | Export document to Markdown |
| `feishu-docx create <TITLE> --user-id <USER_ID>` | Create new document |
| `feishu-docx write <URL> --user-id <USER_ID>` | Append content to document |
| `feishu-docx update <URL> --user-id <USER_ID>` | Update specific block |
| `feishu-docx export-wiki-space <URL> --user-id <USER_ID>` | Batch export entire wiki space |
| `feishu-docx export-workspace-schema <ID> --user-id <USER_ID>` | Export bitable database schema |

## Examples

### Export a wiki page

```bash
feishu-docx export "https://xxx.feishu.cn/wiki/ABC123" -o ./docs --user-id <USER_ID>
```

### Export a document with custom filename

```bash
feishu-docx export "https://xxx.feishu.cn/docx/XYZ789" -o ./docs -n meeting_notes --user-id <USER_ID>
```

### Read content directly (recommended for AI Agent)

```bash
# Output content to stdout instead of saving to file
feishu-docx export "https://xxx.feishu.cn/wiki/ABC123" --stdout --user-id <USER_ID>
# or use short flag
feishu-docx export "https://xxx.feishu.cn/wiki/ABC123" -c --user-id <USER_ID>
```

### Export with Block IDs (for later updates)

```bash
# Include block IDs as HTML comments in the Markdown output
feishu-docx export "https://xxx.feishu.cn/wiki/ABC123" --with-block-ids --user-id <USER_ID>
# or use short flag
feishu-docx export "https://xxx.feishu.cn/wiki/ABC123" -b --user-id <USER_ID>
```

### Batch Export Entire Wiki Space

```bash
# Export all documents in a wiki space (auto-extract space_id from URL)
feishu-docx export-wiki-space "https://xxx.feishu.cn/wiki/ABC123" -o ./wiki_backup --user-id <USER_ID>

# Specify depth limit
feishu-docx export-wiki-space "https://xxx.feishu.cn/wiki/ABC123" -o ./docs --max-depth 3 --user-id <USER_ID>

# Export with Block IDs for later updates
feishu-docx export-wiki-space "https://xxx.feishu.cn/wiki/ABC123" -o ./docs -b --user-id <USER_ID>
```

### Export Database Schema

```bash
# Export bitable/workspace database schema as Markdown
feishu-docx export-workspace-schema <workspace_id> --user-id <USER_ID>

# Specify output file
feishu-docx export-workspace-schema <workspace_id> -o ./schema.md --user-id <USER_ID>
```

## Write Documents (CLI)

### Create Document

```bash
# Create empty document
feishu-docx create "我的笔记" --user-id <USER_ID>

# Create with Markdown content
feishu-docx create "会议记录" -c "# 会议纪要\n\n- 议题一\n- 议题二" --user-id <USER_ID>

# Create from Markdown file
feishu-docx create "周报" -f ./weekly_report.md --user-id <USER_ID>

# Create in specific folder
feishu-docx create "笔记" --folder fldcnXXXXXX --user-id <USER_ID>
```

**如何获取 folder token**:
1. 在浏览器中打开目标文件夹
2. 从 URL 中提取 token：`https://xxx.feishu.cn/drive/folder/fldcnXXXXXX`
3. `fldcnXXXXXX` 就是 folder token

### Append Content to Existing Document

```bash
# Append Markdown content
feishu-docx write "https://xxx.feishu.cn/docx/xxx" -c "## 新章节\n\n内容" --user-id <USER_ID>

# Append from file
feishu-docx write "https://xxx.feishu.cn/docx/xxx" -f ./content.md --user-id <USER_ID>
```

### Update Specific Block

```bash
# Step 1: Export with Block IDs
feishu-docx export "https://xxx.feishu.cn/docx/xxx" -b -o ./ --user-id <USER_ID>

# Step 2: Find block ID from HTML comments
# <!-- block:blk123abc -->
# # Heading
# <!-- /block -->

# Step 3: Update the specific block
feishu-docx update "https://xxx.feishu.cn/docx/xxx" -b blk123abc -c "新内容" --user-id <USER_ID>
```

> **Tip for AI Agents**: When you need to update a specific section:
> 1. Export with `-b` to get block IDs
> 2. Find the target block ID from HTML comments
> 3. Use `feishu-docx update` with that block ID

## Tips

- Images auto-download to `{doc_title}/` folder
- Use `--stdout` or `-c` for direct content output (recommended for agents)
- Use `-b` to export with block IDs for later updates
- For Lark (overseas): add `--lark` flag
