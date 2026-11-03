"""
Environment Diagnostic, Dependency Verification, and Auto-Repair Hub (da doctor)
"""
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
    "rookiepy": ("rookiepy>=0.4.0", "原生静默读取 Chrome/Safari 默认浏览器 Cookie", True),
    "yt_dlp": ("yt-dlp>=2024.0.0", "YouTube/Twitter/Instagram 全球社交音视频提取器", True),
}

EXTERNAL_TOOLS = {
    "curl": ("系统原生流式网络下载工具，用于极端环境兜底", True),
    "ffmpeg": ("音视频流合并与无损格式探测（可选）", False),
}

class Doctor:
    """Diagnoses environment readiness, missing libraries, and provides automatic fixes."""

    @staticmethod
    def check_all() -> Dict[str, Any]:
        """Perform full diagnostic sweep."""
        report = {
            "python_version": {
                "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "ok": sys.version_info >= (3, 10),
                "required": ">=3.10"
            },
            "dependencies": {},
            "external_tools": {},
            "mac_fda": None,
            "all_required_ok": True,
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
            report["external_tools"][tool] = {
                "installed": bool(path),
                "path": path,
                "description": desc,
                "required": is_req,
            }
            if is_req and not path:
                report["all_required_ok"] = False

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
    def auto_repair() -> bool:
        """
        Automatically install missing Python dependencies using uv (fast) or pip.
        Returns True if all required dependencies succeed.
        """
        report = Doctor.check_all()
        missing = [
            info["pip_name"]
            for info in report["dependencies"].values()
            if not info["installed"]
        ]

        if not missing:
            return True

        has_uv = bool(shutil.which("uv"))
        py_executable = sys.executable

        if has_uv:
            cmd = ["uv", "pip", "install"] + missing
        else:
            cmd = [py_executable, "-m", "pip", "install"] + missing

        try:
            res = subprocess.run(cmd, check=True)
            return res.returncode == 0
        except Exception:
            return False
