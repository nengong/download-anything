# Download Anything (DA)

> **全能微资产（<500MB）提取与离线沉淀中枢**  
> 轻量极速 · 零虚假成功 · 全要素伴生 · 多源驱动插拔

---

## 🎯 核心定位与原则

市面上的下载工具普遍存在“专攻单一媒体类型”、“忽略中国本土复杂风控生态”、“粗暴单文件落盘丢失元数据”等问题。`Download Anything` 聚焦于解决 **500MB 以内高信息密度资产的精准摄取**。

1. **输入杂质免疫（Dirty Link Immune）**：平台分享文本（广告、换行、中文、短链）自动清洗。
2. **伴生资产全要素沉淀（Sidecar Metadata）**：下载主资产时，伴生标准元数据 JSON、正文 Markdown、封面图及字幕。
3. **零假死与零虚假成功（Zero False-Positive Verification）**：拒绝“>10KB 即成功”，通过 `Content-Length` 比对与文件魔数（PDF EOF、EPUB 容器、图片解析等）深度自检。
4. **静默原子闭环（Headless Automation）**：针对网盘小文件的强制转存限制，后台自动完成 `静默转存 ➔ 提取高速直链 ➔ 本地落盘 ➔ 自动销毁网盘副本`。
5. **双模输出（Dual-Mode Interface）**：
   - **人类模式（Human CLI）**：彩色状态卡、进度条。
   - **Agent 模式（Agent Skill JSON）**：带 `--json` 标志，向 stdout 输出标准资产 JSON。

---

## 🚀 快速上手

### 1. 安装依赖

```bash
uv pip install -e ".[dev]"
```

### 2. 执行入口

```bash
# 方式 1：通过 bin/da
./bin/da "<任意URL或口令>"

# 方式 2：使用 uv 运行
uv run da "<任意URL或口令>"
```

### 3. Agent 模式（输出标准 JSON）

```bash
da "<URL>" --json
```

---

## 📦 架构概览

- `core/router.py`: 智能 URL 清洗与驱动路由分发
- `core/fetcher.py`: 流式分块断点下载与超时防截断引擎
- `core/verifier.py`: 格式魔数深度自检器
- `core/sidecar.py`: 资产伴生生成器 (`content.info.json` + `content.md`)
- `drivers/`: 模块化驱动池（蓝奏云、夸克网盘、Shadow Library 等）
