"""
Environment Diagnostic, Dependency Verification, and Auto-Repair Hub (da doctor)
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List

# Core dependency map: package_import_name -> (pip_name, description, required)
DEPENDENCY_SPEC = {
    "requests": ("requests>=2.31.0", "HTTP/HTTPS 流式网络引擎与重试机制", True),
    "rich": ("rich>=13.7.1", "终端彩色进度条、状态卡片与双模渲染", True),
    "click": ("click>=8.1.7", "现代化命令行解析与子命令路由", True),
    "yaml": ("pyyaml>=6.0.1", "本地凭据与全局配置管理", True),
    "bs4": ("beautifulsoup4>=4.12.3", "HTML/XML 页面反爬解析与正文清洗", True),
    "PIL": ("pillow>=10.3.0", "图片魔数深度自检与防 403 陷阱检测", True),
    "pypdf": ("pypdf>=4.2.0", "PDF 结构完整性与 EOF 签名验收", True),
    "cryptography": ("cryptography>=42.0.0", "跨平台 Chromium/Keychain 本地 Cookie 解密", True),
    "rookiepy": ("rookiepy>=0.4.0", "原生静默读取 Chrome/Safari 默认浏览器 Cookie（可选增强，缺省时自动回退本地 Cookie 库）", False),
    "yt_dlp": ("yt-dlp>=2024.0.0", "YouTube/Twitter/Instagram 及通用 yt-dlp 兜底提取器", True),
    "gallery_dl": ("gallery-dl>=1.32.19", "X/Instagram/微博图片提取后端", True),
}

EXTERNAL_TOOLS = {
    "curl": ("系统原生流式网络下载工具，用于极端环境兜底", True),
    "ffmpeg": ("音视频抽轨、转码与流合并（仅音视频功能需要）", False),
    "ffprobe": ("音视频结构校验（仅下载音视频时需要；随 FFmpeg 提供）", False),
}

# FFmpeg is a media-only dependency: every other driver keeps working without it.
MEDIA_TOOL_SCOPE = {
    "ffmpeg": {
        "scope": "仅音视频",
        "affects": ["音频提取", "格式转码", "音视频流合并"],
        "unaffected": ["文档", "论文", "电子书", "图片", "网盘", "网页/文章"],
    },
    "ffprobe": {
        "scope": "仅音视频",
        "affects": ["音视频结构完整性校验"],
        "unaffected": ["文档", "论文", "电子书", "图片", "网盘", "网页/文章"],
    },
}

MEDIA_TOOL_INSTALL = {
    "darwin": "brew install ffmpeg",
    "win32": "winget install -e --id Gyan.FFmpeg",
    "linux": "sudo apt install ffmpeg  # Debian/Ubuntu；Fedora 用 sudo dnf install ffmpeg",
}

# Install commands for bootstrapping a Python new enough for the CLI.
PYTHON_INSTALL = {
    "darwin": "brew install python@3.12   # 或安装 uv：brew install uv",
    "win32": "winget install -e --id Python.Python.3.12",
    "linux": "sudo apt install python3.12 python3.12-venv   # Debian/Ubuntu；Fedora 用 sudo dnf install python3.12",
}


def _platform_key():
    return "darwin" if sys.platform == "darwin" else "win32" if sys.platform == "win32" else "linux"

PYPI_MIRRORS = (
    ("清华镜像", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里云镜像", "https://mirrors.aliyun.com/pypi/simple/"),
)

class Doctor:
    """Diagnoses environment readiness, missing libraries, and provides automatic fixes."""

    @staticmethod
    def python_install_hint() -> str:
        return PYTHON_INSTALL[_platform_key()]

    @staticmethod
    def check_all() -> Dict[str, Any]:
        """Perform full diagnostic sweep."""
        report = {
            "python_version": {
                "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "ok": sys.version_info >= (3, 10),
                "required": ">=3.10",
                "install_hint": Doctor.python_install_hint(),
            },
            "dependencies": {},
            "external_tools": {},
            "mac_fda": None,
            "media_ready": False,
            "all_required_ok": sys.version_info >= (3, 10),
        }

        # 1. Check Python packages
        import importlib.metadata
        for mod_name, (pip_name, desc, is_req) in DEPENDENCY_SPEC.items():
            installed = False
            version = None
            try:
                mod = __import__(mod_name)
                installed = True
                pkg_name = pip_name.split(">=")[0]
                try:
                    version = importlib.metadata.version(pkg_name)
                except Exception:
                    version = getattr(mod, "__version__", "installed")
            except ImportError:
                pass

            report["dependencies"][mod_name] = {
                "pip_name": pip_name,
                "description": desc,
                "installed": installed,
                "version": str(version) if version else None,
                "required": is_req,
            }
            if is_req and not installed:
                report["all_required_ok"] = False

        # 2. Check External Tools
        for tool, (desc, is_req) in EXTERNAL_TOOLS.items():
            path = shutil.which(tool)
            info = {
                "installed": bool(path),
                "path": path,
                "description": desc,
                "required": is_req,
            }
            if tool in MEDIA_TOOL_SCOPE:
                info.update(MEDIA_TOOL_SCOPE[tool])
                info["install_hint"] = MEDIA_TOOL_INSTALL[_platform_key()]
            report["external_tools"][tool] = info
            if is_req and not path:
                report["all_required_ok"] = False

        report["media_ready"] = all(
            report["external_tools"][tool]["installed"] for tool in MEDIA_TOOL_SCOPE
        )

        # 3. macOS Full Disk Access (FDA) check
        if sys.platform == "darwin":
            chrome_cookie_path = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
            has_fda = False
            if chrome_cookie_path.exists():
                try:
                    with open(chrome_cookie_path, "rb") as f:
                        f.read(16)
                    has_fda = True
                except PermissionError:
                    has_fda = False
                except Exception:
                    has_fda = True
            report["mac_fda"] = {
                "enabled": has_fda,
                "description": "macOS 完全磁盘访问权限（开启后可 0 交互静默读取 Chrome/Safari 登录凭据）"
            }

        return report

    @staticmethod
    def auto_repair(capture_output: bool = False) -> bool:
        """
        Automatically install missing Python dependencies using uv (fast) or pip.
        Returns True if all required dependencies succeed.
        """
        if sys.version_info < (3, 10):
            # Installing dependencies cannot fix an interpreter that is too old.
            return False

        report = Doctor.check_all()
        missing = [
            info["pip_name"]
            for info in report["dependencies"].values()
            if not info["installed"] and info.get("required", True)
        ]

        if not missing:
            return True

        has_uv = bool(shutil.which("uv"))
        py_executable = sys.executable

        if has_uv:
            base = ["uv", "pip", "install", "--python", py_executable]
        else:
            base = [py_executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--timeout", "25", "--retries", "1"]

        output_options = (
            {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
            if capture_output
            else {}
        )
        env = dict(os.environ)
        env.setdefault("UV_HTTP_TIMEOUT", "50")
        sources = [("官方 PyPI", None)] + list(PYPI_MIRRORS)
        custom = os.environ.get("DA_PIP_INDEX_URL", "").strip()
        if custom:
            sources.insert(0, ("自定义源 DA_PIP_INDEX_URL", custom))
        for _label, index_url in sources:
            cmd = list(base)
            if index_url:
                cmd += ["--index-url", index_url]
            cmd += missing
            try:
                res = subprocess.run(cmd, check=True, timeout=1800, env=env, **output_options)
                if res.returncode == 0:
                    return True
            except Exception:
                continue
        return False
