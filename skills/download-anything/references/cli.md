# CLI 与结果协议

本文使用 `da` 代指已经安装的 CLI。源码入口也可用仓库的 `bin/da`。

## 参数

| 参数 | 用途 |
| --- | --- |
| `TARGETS...` | URL、分享文本、DOI、MD5、书名/ISBN 或本地音频路径 |
| `-i, --input-file FILE` | 一行一个目标，忽略空行及 `#` 注释；串行处理 |
| `-o, --output-dir PATH` | 保存根目录，每次按日期和标题创建子目录 |
| `-p, --password TEXT` | 分享提取码或 ZIP 密码 |
| `--lang LANG` | 语言偏好（如 `zh`、`en`），依据使用者对话语言设定，高权重优先匹配对应语言版本 |
| `-a, --audio, --audio-only` | 提取纯音轨，必要时调用 ffmpeg |
| `-f, --force` | 跳过本地缓存，重新解析和下载 |
| `--vault PATH, --obsidian PATH` | 同步至指定 Obsidian 目录，均需路径 |
| `--notion` | 创建 Notion 短记录，需要 NOTION_API_KEY 与 NOTION_DATABASE_ID |
| `--transcribe` | 将音频提交配置的云端转写服务 |
| `--unzip / --no-unzip` | 默认尝试受限 ZIP/TAR 解压 |
| `--max-mb N` | 单文件下载限制，正整数，默认 500 MB |
| `--check` | 预检元数据；网盘不转存，本地音频不转码 |
| `--no-sidecar` | 不额外生成元数据 JSON、Markdown 或歌词 |
| `--json` | 机器可读结果，下载时抑制进度条 |
| `-v, --verbose` | 人类模式诊断信息 |
| `doctor [--fix] [--json]` | 检查依赖；fix 安装缺少的 Python 包，不安装 FFmpeg |
| `login PLATFORM [--json]` | 从本机已登录浏览器/客户端读取目标平台 Cookie 并保存；某些本机工具会弹出登录窗口 |

默认输出优先级：`-o`、`DA_OUTPUT_DIR`、用户项目内已有的下载/资产目录、系统 Downloads 下的 DA 文件夹。缓存记录位于 `~/.download-anything/index.db`，保存的凭据位于 `~/.download-anything/credentials.yaml`，凭据文件权限为 0600。

## JSON

成功输出包括 `status`、`platform`、`title`、`output_dir`、`primary_asset`、`size_bytes`、`sidecars`、`companion_files`、`extracted_files`、`verification`、`warnings`、`operations`。

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

`warnings` 为空列表时没有已知的附属步骤失败。`operations` 按需包含 `transcription`、`obsidian`、`notion` 和 `cleanup`，每步提供 `status`，失败/跳过时提供 `reason`。

伴生件可能有 `info_json`、`markdown`、`named_info_json`、`named_markdown`、`cover`、`subtitle`、`lyrics`、`transcript`、`obsidian_vault_note`、`notion_page`。不得推定所有键必然存在；生成文件若与下载资产重名，会添加 `.metadata` 避免覆盖。

缓存结果的 `status` 为 `cached`，另有 `cached: true`、`sha256`、`created_at`；不保证提供下载时的全部顶层字段。媒体检查的 `level` 为 `media-structure`；普通格式为 `basic`；缓存复用为 `cached-existence`。加密 ZIP 仅在解压前识别容器，`level: encrypted-container`、`crc_checked: false` 不代表内容已验证。

预检返回 `status: dry_run`，`primary_asset` 改为包含 `filename`、`url`、`expected_size`、`file_type` 的对象；另有 `metadata`、`total_assets`。网盘直链为空，不能把它直接交给下载器。

错误对象为 `status: error`、`error_type`、`message`，可能附带 `details`。批量对象为 `batch: true`、`total`、`success_count`、`partial_count`、`results`；每项包含 `target`。

## 常见失败

- `AuthenticationRequiredError`：目标平台需要登录；不要改用无关账号或输出 Cookie。
- `VerificationError`：格式、结构或长度不符；刷新一次仍失败就报告具体原因。缺少 ffprobe 时必须先安装 FFmpeg。
- `FileTooLargeError`：下载或解压超限；下载上限和解压上限是独立的。
- `CloudDriveError`：网盘查询/转存/清理未确认；读取 `details.cleanup_error` 并交代可能的残留，不要盲目删除旧目录。
- `ExtractionError`：提取失败、ZIP 密码问题或不支持的安全解压格式；可用 `--no-unzip` 只保存原包。
- CLI 在导入时崩溃：运行 Skill 的 `scripts/install.py` 重建依赖，不能依赖尚无法启动的 doctor 自愈。
