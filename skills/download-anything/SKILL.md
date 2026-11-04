---
name: download-anything
description: 用 DA CLI 将视频、图片、文章、文档、音频、论文和网盘分享保存为本地文件，并保留可获取的正文和元数据。用于明确要求下载或离线归档的任务；默认每个文件不超过 500 MB。GitHub 文件和目录优先使用既有 GitHub CLI/MCP。平台适配仍属实验性，不用于直播录制或绕过私有文档权限。
---

# Download Anything

把用户指定的内容保存到本地，检查实际文件，并向用户交代完整交付、部分完成或失败。平台驱动是否能运行取决于站点、登录态及当前访问条件；注册驱动不代表已经完成真实平台验收。

## 找到或安装 CLI

1. 优先使用 PATH 中的 `da`，或用户指定的 DA 安装位置。
2. 若 PATH 中没有，检查默认独立环境：macOS/Linux 为 `~/.download-anything/venv/bin/da`，Windows 为 `%USERPROFILE%\.download-anything\venv\Scripts\da.exe`。
3. 尚未安装时，用 Python 3.10 或更高版本运行**本 Skill 目录中的** `scripts/install.py`。例如 `python3 /实际的Skill目录/scripts/install.py`。脚本从发布 ZIP 附带的 `assets/*.whl` 安装 CLI 和依赖至上述独立环境，不需要先启动 DA。
4. 源码仓库中的同一个安装脚本也能安装当前仓库。若仅有一个 SKILL.md 而没有程序/安装脚本，说明分发物不完整，停止并说明缺失项。
5. 运行 `da doctor --json` 检查环境。音视频校验必须有 `ffprobe`；抽轨和转码需要 `ffmpeg`，两者随 FFmpeg 一起提供。CLI 因缺 Python 依赖无法启动时，重新运行安装脚本；能启动时才用 `da doctor --fix --json`。

安装脚本也接受 `--venv /目标环境路径`。不要把某台机器上的开发目录当成通用启动位置。

## 执行流程

- GitHub 文件、目录和仓库任务优先交给用户已有并授权的 GitHub CLI/MCP。DA 中保留的 GitHub 驱动属实验性兼容能力，不作为首发验收门槛，不主动重复实现现有工具已能完成的获取任务。
- 自动化调用使用 `--json`，解析 stdout 的 JSON；参数拼错等 CLI 解析错误可能只出现在 stderr，仍需检查退出码。
- 默认使用 `da "目标链接或本地音频路径" --json`。批量用 `-i links.txt`，一行一个目标，`#` 开头为注释；批量任务串行执行。
- 电子书下载支持直接输入书名、作者或 ISBN（如 `da "哲学谈话录" --json` 或 `da "book:Thinking Fast and Slow" --json`）。**必须根据当前对话中与使用者交流的语言设定语言优先级**：与用户用中文沟通时传 `--lang zh`（中文版本优先），与用户用英文沟通时传 `--lang en`（英文版本优先）；驱动将在影子图书馆多镜像中检索、按对话语言高权重打分并自动解析直链。
- 下载前只想查看元数据时用 `--check`。网盘预检不转存、不创建目录、不申请下载链接，`primary_asset.url` 因此可能为空，需检查 `metadata.requires_transfer`。本地音频预检不转码。
- 默认每个下载文件上限 500 MB，解压另有总量 500 MB / 10000 成员限制。用户要求更大下载时可设置 `--max-mb N`；提高下载上限不会提高解压上限。
- 纯音频用 `-a`。音频云端转写用 `--transcribe`；视频应同时用 `-a`。转写会把音频发给配置的云服务，不能仅凭环境里有 API key 就自行启动转写。
- 同步 Obsidian 用 `--vault /vault路径` 或 `--obsidian /vault路径`，两个选项均需要路径值。环境变量 `OBSIDIAN_VAULT_PATH` / `DA_VAULT_PATH` 也会触发同步，执行前留意用户预期的保存位置。
- `--notion` 会创建远端 Notion 记录，仅在用户要求同步时使用。当前写入为短记录，正文最多 1500 字符，不代表完整文档备份。
- 网盘实际下载会创建本次任务专用的 `_da_temp_<随机值>` 目录并转存文件，结束或失败后尝试清理；必须检查清理结果，不能承诺云端无残留。

详细参数、JSON 字段和异常处理见 [references/cli.md](references/cli.md)。平台覆盖与已知限制见 [references/platforms.md](references/platforms.md)。

## 判断结果

- `status: success`：主文件通过当前格式的检查，提取出的附件和请求的后续步骤已完成。也要查看 `verification.details.level`；普通格式只做基础检查。
- `status: cached`：复用历史产物，检查文件存在和大小，未重算 SHA256 或重新解析媒体。需要重新下载时加 `-f`。
- `status: partial`：主文件已保存，但存在附件、转写、同步或清理失败；读取 `warnings` 和 `operations`，明确说明缺了什么。单任务及包含部分完成项的批量命令返回退出码 2。
- `status: dry_run`：只完成预检，没有交付下载文件。
- `status: error`：读取 `error_type`、`message` 和可选 `details`。不得将错误、部分完成或预检描述为完整下载成功。
- 批量必须逐项解析 `results[].status`。`success_count` 不包含 `partial`，`partial_count` 单独统计；存在部分完成项时退出码 2，否则仍沿用至少一项完整成功返回 0、全部失败返回 1 的约定。

失败后只做有依据的有限重试：失效直链或网络错误可强制刷新一次；认证失败先检查目标平台的已配置凭据，必要时使用 `da login 平台 --json`。不要输出 Cookie、API key 或含凭据的请求头，也不要无限循环登录、转存或下载。

自动解压只支持受限 ZIP/TAR；归档链接、特殊文件、7z/RAR 或不支持的加密方式会失败，用户只需保留原包时加 `--no-unzip`。不得为了兼容性调用不受约束的外部解压器。
