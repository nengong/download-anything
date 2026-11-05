# CLI 与结果协议

本文使用 `da`（或同义别名 `dl`）代指已安装的 CLI，源码仓库也可直接调用 `bin/da`。

## 参数

| 参数 | 用途 |
| --- | --- |
| `TARGETS...` | URL、分享文本、DOI、ISBN、MD5、包名/产品 ID 或本地音频路径 |
| `-i, --input-file FILE` | 一行一个目标，忽略空行及 `#` 注释；按顺序串行处理 |
| `-o, --output-dir PATH` | 保存根目录，每次按日期和标题创建独立子目录，同名目录自动编号 |
| `-p, --password TEXT` | 分享提取码或 ZIP 解压密码 |
| `-a, --audio, --audio-only` | 提取纯音轨（`.m4a` / `.mp3`） |
| `-f, --force` | 跳过本地缓存，重新解析和下载 |
| `--vault PATH, --obsidian PATH` | 同步至指定 Obsidian Vault 目录（自动注入 YAML frontmatter） |
| `--notion` | 将摘要记录同步至 Notion 数据库（需配置 `NOTION_API_KEY` 与 `NOTION_DATABASE_ID`） |
| `--transcribe` | 调用云端 Whisper 接口生成带时间戳的 `.transcript.md` 文字稿（需配置 `GROQ_API_KEY`、`OPENAI_API_KEY` 或 `SILICONFLOW_KEY`） |
| `--unzip / --no-unzip` | 默认自动执行受限 ZIP/TAR 解压；加 `--no-unzip` 保留原压缩包 |
| `--max-mb N` | 单文件下载大小上限（正整数，默认 500 MB） |
| `--check` | 仅预检目标元数据与大小 |
| `--no-sidecar` | 不生成伴生 `.info.json`、Markdown 或 `.lrc` 歌词文件 |
| `--json` | 输出机器可读 JSON 结果，下载时抑制进度条 |
| `-v, --verbose` | 输出详细诊断信息 |
| `doctor [--fix] [--json]` | 检查运行环境与依赖；`--fix` 自动安装缺失的 Python 包（官方源超时自动切换国内镜像） |
| `login PLATFORM [--json]` | 从本机已登录浏览器或客户端提取目标平台 Cookie 并保存 |

默认输出目录优先级：`-o` → `DA_OUTPUT_DIR` → 当前项目内已有的下载/资产目录 → 系统 `Downloads` 下的 `DA` 文件夹。本地缓存索引位于 `~/.download-anything/index.db`，凭据配置文件位于 `~/.download-anything/credentials.yaml`（权限 `0600`）。

## 常用示例

```bash
# 按 ISBN 或 MD5 下载电子书
da "9780141439518" --json
da "51860b9694a6d153c4c305dcf3b9e10d" --json

# 下载小宇宙或 Apple Podcasts 播客单集
da "https://www.xiaoyuzhoufm.com/episode/..." --json

# 本地音频转 MP3
da "/path/to/audio.ncm" --json
da "/path/to/audio.flac" --json
```

## JSON 结果结构

下载结果包含 `status`、`platform`、`title`、`output_dir`、`primary_asset`、`size_bytes`、`sidecars`、`companion_files`、`extracted_files`、`verification`、`warnings`、`operations`：

```json
{
  "status": "partial",
  "platform": "example",
  "title": "Example",
  "primary_asset": "/downloads/Example.txt",
  "size_bytes": 100,
  "verification": {"valid": true, "detected_type": "binary/txt", "details": {"level": "basic"}},
  "warnings": [{"stage": "companion", "asset": "second.jpg", "message": "Download failed"}],
  "operations": {"cleanup": {"status": "success"}}
}
```

- **伴生与附属文件**：`sidecars` 按实际生成情况包含 `info_json`、`markdown`、`named_info_json`、`named_markdown`、`cover`、`subtitle`、`lyrics`（`.lrc` 歌词）、`transcript`（语音转写稿）、`obsidian_vault_note`、`notion_page`；多图、文章插图或 `citation.bib` 等附属资产路径记录在 `companion_files` 列表中。
- **后续操作状态**：`operations` 按需记录 `transcription`、`obsidian`、`notion` 与 `cleanup` 的执行状态（`status` 及原因 `reason`）。
- **校验级别（`verification.details.level`）**：音视频结构扫描为 `media-structure`，常规格式为 `basic`，加密 ZIP 容器识别为 `encrypted-container`，本地缓存复用为 `cached-existence`。
- **缓存命中（`status: cached`）**：当 URL 与下载参数（音频、解压、伴生文件等）一致且本地交付文件完整时，返回 `cached: true`、`primary_asset`、`output_dir`、`size_bytes`、`sha256`、`sidecars` 与 `created_at`。
- **元数据预检（`status: dry_run`）**：`primary_asset` 为包含 `filename`、`url`、`expected_size`、`file_type` 的描述对象，并附带 `metadata` 与 `total_assets`。
- **批量结果（`batch: true`）**：包含 `total`、`success_count`、`partial_count` 与 `results` 列表（每项带 `target` 字段）。

## 错误类型

错误输出结构为 `status: error`、`error_type`、`message` 及可选 `details`：

- `AuthenticationRequiredError`：目标平台需要登录凭据（可通过 `da login <平台> --json` 配置）。
- `VerificationError`：主文件格式、媒体结构或字节长度校验未通过（音视频校验需安装 `ffprobe`）。
- `FileTooLargeError`：下载文件或解压归档超过大小/成员数限制。
- `CloudDriveError`：网盘分享访问、临时转存或目录清理异常（清理异常详情见 `details.cleanup_error`）。
- `ExtractionError`：页面解析失败、ZIP 密码不匹配或压缩包格式需要加 `--no-unzip` 保留原包。
