# Download Anything (DA)

将链接中的内容保存为本地文件，并保留可获取的正文、图片、字幕和元数据。默认每个下载文件不超过 500 MB，提供 CLI 和 Agent Skill 两种入口。

当前版本为 0.1.0。27 个站点/内容驱动仍属实验性；工程回归通过不代表所有平台已完成真实联调。平台限制见 Skill 中的 `references/platforms.md`。

GitHub 文件与目录获取优先使用已有 GitHub CLI/MCP。现有 GitHub 驱动保留为实验性兼容能力，其目录下载不纳入首发稳定承诺，也不阻塞本版发布。

## 安装

需要 Python 3.10 或更高版本。音视频校验需要 `ffprobe`，抽轨/转码需要 `ffmpeg`；二者均随 FFmpeg 提供，安装后应能从 PATH 找到。

从源码目录安装到独立环境：

```bash
python3 skills/download-anything/scripts/install.py
~/.download-anything/venv/bin/da doctor --json
```

将该环境的 `bin` 加入 PATH 后即可使用 `da` / `dl`。Windows 对应目录为 `%USERPROFILE%\.download-anything\venv\Scripts`。已有环境需要升级或修复 Python 依赖时重新运行安装脚本，也可指定 `--venv /自选环境路径`。

安装完整 Skill 发布 ZIP 时，先解压，再运行其中的 `download-anything/scripts/install.py`。ZIP 同时包含 Skill、安装脚本及 CLI wheel；单独复制 SKILL.md 不足以安装程序。

如果 CLI 已能启动，`da doctor --fix --json` 可以补齐 Python 依赖；启动前就缺少 click 等依赖时，需要使用独立安装脚本。doctor 不会自动安装 FFmpeg。

卸载程序时删除安装时选择的虚拟环境，并删除自己添加的 PATH 配置。`~/.download-anything/index.db`、`credentials.yaml` 和已下载文件不会随虚拟环境删除；保留或删除由用户自行决定。

## 使用

```bash
da "目标链接" --json
da "目标链接" --check --json
da "视频链接" -a --transcribe --json
da -i links.txt --json
da "目标链接" --vault ~/Documents/MyVault --json
da "目标链接" --notion --json
```

- 批量列表一行一个目标，支持空行和 `#` 注释，任务串行执行。
- `-o` 指定保存目录。未指定时还会考虑 `DA_OUTPUT_DIR`、用户项目已有的资产目录以及系统 Downloads。
- `-f` 强制重新下载。默认缓存保留原 URL 大小写，按主文件存在和大小判断可复用，不重算 SHA256。
- `--no-sidecar` 禁止额外生成元数据文件；伴生文件自动避让下载资产路径，不覆盖原文。
- `--max-mb N` 改变单个下载文件上限；自动解压的总量上限仍为 500 MB / 10000 个成员。
- 自动解压只支持受限 ZIP/TAR，拒绝链接及特殊文件；7z/RAR 或不支持的加密压缩包可加 `--no-unzip` 保存原包。
- Obsidian 的 `--vault` / `--obsidian` 都必须传路径。`OBSIDIAN_VAULT_PATH` / `DA_VAULT_PATH` 环境变量同样触发同步。
- `--transcribe` 会将音频上传至配置的云服务，需要 GROQ_API_KEY、OPENAI_API_KEY 或 SILICONFLOW_KEY。视频应配合 `-a`。
- `--notion` 会创建 Notion 短记录，需要 NOTION_API_KEY 和 NOTION_DATABASE_ID。当前正文最多写入 1500 字符。
- 百度/夸克实际下载会使用本次任务专属临时目录转存文件，结束或失败后尝试清理。清理失败会明确报告；预检不做转存。

## 判断结果

自动化调用应解析 JSON，不能仅看退出码。

| status | 含义 |
| --- | --- |
| success | 当前提取出的产物及请求步骤已完成 |
| cached | 复用历史文件；没有重新执行完整性检查 |
| partial | 主文件已保存，但附件、转写、同步或清理有失败；查看 warnings / operations |
| dry_run | 仅预检，没有交付下载文件 |
| error | 下载或主文件验收失败 |

单任务成功/缓存/预检返回 0，部分完成返回 2，失败返回 1。批量存在部分完成项时返回 2；否则至少一项完整成功返回 0、全部失败返回 1。批量 `success_count` 不包含 `partial`，需逐项检查 `results[].status`。

PDF、图片、ZIP 使用格式对应检查；媒体借助 ffprobe 扫描轨道和可读数据包。`verification.details.level` 说明检查级别，普通未知格式只做基础检查。这些检查不构成“零虚假成功”、发布者签名认证或完整解码保证。

## 开发与打包

```bash
uv pip install -e '.[dev]'
.venv/bin/python -m pytest -q
python3 scripts/build_release.py
```

没有 uv 时也可在虚拟环境中用 `python -m pip install -e '.[dev]'`。构建脚本生成 `dist/` 下的 CLI wheel 和完整 Skill ZIP，不执行上传。依赖在安装时解析下载，发布 ZIP 不包含所有第三方依赖，因此不是完全离线安装包。

CI 验证测试、打包和仓库外的 Skill 安装。真实平台联调、实际登录、网盘生命周期和收费转写仍需另行验收后才能解除相应实验性标记。

MIT License，见 LICENSE。
