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
| `--transcribe` | 可选扩展：调用外部语音转写服务生成带时间戳的 `.transcript.md` 文字稿（常规下载、字幕提取与本地音轨处理均纯本地免配置运行） |
| `--unzip / --no-unzip` | 默认自动执行受限 ZIP/TAR 解压；加 `--no-unzip` 保留原压缩包 |
| `--max-mb N` | 单文件下载大小上限（正整数，默认 500 MB） |
| `--check` | 仅预检目标元数据与大小 |
| `--no-sidecar` | 不生成伴生 `.info.json`、Markdown 或 `.lrc` 歌词文件 |
| `--json` | 输出机器可读 JSON 结果，下载时抑制进度条 |
| `-v, --verbose` | 输出详细诊断信息 |
| `doctor [--fix] [--json]` | 检查运行环境与依赖；`--fix` 自动安装缺失的 Python 包（官方源超时自动切换国内镜像） |
| `login PLATFORM [--json]` | 从本机已登录浏览器或客户端提取目标平台 Cookie 并保存 |

默认输出目录优先级：`-o` → `DA_OUTPUT_DIR` → 当前项目内已有的下载/资产目录 → 系统 `Downloads` 下的 `DA` 文件夹。本地缓存索引位于 `~/.download-anything/index.db`，凭据配置文件位于 `~/.download-anything/credentials.yaml`（权限 `0600`）。

### 凭据解析优先级与无头环境（Headless）支持

平台凭据按如下优先级自动解析：
1. **环境变量**：优先 `DA_<PLATFORM>_COOKIE`；同时兼容 `<PLATFORM>_COOKIE`，例如 `DA_BAIDU_COOKIE` 优先于 `BAIDU_COOKIE`。Instagram 多图使用 `DA_INSTAGRAM_COOKIE_FILE` 指向授权 Cookie 文件。
2. **本地配置文件**：`~/.download-anything/credentials.yaml` 及项目内 `config/credentials.yaml` 兜底；自行预置的文件应设置为 `0600`。
3. **本机活跃浏览器 Cookie**：通过 `rookiepy` 静默提取 Chrome、Arc、Edge、Brave、Safari、Firefox 登录态（限桌面环境）。
4. **桌面客户端本地数据库与系统钥匙串**：提取百度网盘/夸克网盘桌面端已登录数据库及 macOS 系统钥匙串。

### 大文件预检与 Agent 命令超时保护

- **预检模式（`--check`）**：针对网盘分享文件、高清长视频或未知体积资源，建议先执行 `da "<目标>" --check --json` 探测元数据与 `expected_size`。百度与夸克预检不触发云端转存与实际落盘。
- **规避 Agent 命令等待超时**：若预检发现文件达到数百 MB 或 GB 级别，Agent 需：
  1. 将终端工具调用的等待超时调大至充足时间，避免进程被过早强杀；
  2. 针对超过 500 MB 的单文件，主动追加 `--max-mb <容量>`（如 `--max-mb 2048`）；
  3. 在支持后台任务的 Agent 框架中，建议将大任务以 daemon/background 模式启动，后续检查状态。

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

- **配套元数据与附属文件**：`sidecars` 按实际生成情况包含 `info_json`、`markdown`、`named_info_json`、`named_markdown`、`cover`、`subtitle`、`lyrics`（`.lrc` 歌词）、`transcript`（语音转写稿）、`obsidian_vault_note`；多图、文章插图或 `citation.bib` 等附属文件路径记录在 `companion_files` 列表中。
- **后续操作状态**：`operations` 按需记录 `transcription`、`obsidian` 与 `cleanup` 的执行状态（`status` 及原因 `reason`）。
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
