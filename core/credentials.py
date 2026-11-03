"""
Unified Credential and Cookie Bridge
"""
import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import yaml

class CredentialsManager:
    """Resolves platform credentials from Env, Config file, or macOS Keychain."""

    KEYCHAIN_SERVICE_MAP = {
        "quark": ["quark", "quark-cookie", "Quark Safe Storage", "QuarkCloudDrive Safe Storage"],
        "baidu": ["baidu", "baidu-cookie", "BaiduNetdisk"],
        "xiaohongshu": ["xiaohongshu", "xhs", "xhs-cookie"],
        "bilibili": ["bilibili", "bilibili-sessdata"],
    }

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(__file__).resolve().parent.parent / "config"
        self.config_dir = config_dir
        self._cached_yaml: Optional[Dict[str, Any]] = None

    def _load_yaml(self) -> Dict[str, Any]:
        if self._cached_yaml is not None:
            return self._cached_yaml

        cred_file = self.config_dir / "credentials.yaml"
        if cred_file.exists():
            try:
                with open(cred_file, "r", encoding="utf-8") as f:
                    self._cached_yaml = yaml.safe_load(f) or {}
                    return self._cached_yaml
            except Exception:
                pass
        self._cached_yaml = {}
        return self._cached_yaml

    def _query_keychain(self, service: str) -> Optional[str]:
        """Query macOS Keychain via `/usr/bin/security`."""
        try:
            cmd = ["/usr/bin/security", "find-generic-password", "-s", service, "-w"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=2)
            if result.returncode == 0 and result.stdout:
                val = result.stdout.strip()
                if val:
                    return val
        except Exception:
            pass
        return None

    def get_credential(self, platform: str, key: str = "cookie") -> Optional[str]:
        """
        Lookup credentials in priority order:
        1. Environment variable: DA_<PLATFORM>_<KEY> (e.g. DA_QUARK_COOKIE)
        2. config/credentials.yaml
        3. macOS Keychain
        """
        # 1. Environment Variable
        env_key = f"DA_{platform.upper()}_{key.upper()}"
        if env_key in os.environ and os.environ[env_key].strip():
            return os.environ[env_key].strip()

        # 2. YAML file
        data = self._load_yaml()
        # Look in nested dicts: pan.quark.cookie or quark.cookie
        for section in ("pan", "social", "books", "docs", "audio", "dev"):
            if section in data and platform in data[section]:
                plat_data = data[section][platform]
                if isinstance(plat_data, dict) and key in plat_data and plat_data[key]:
                    return str(plat_data[key]).strip()
        if platform in data:
            plat_data = data[platform]
            if isinstance(plat_data, dict) and key in plat_data and plat_data[key]:
                return str(plat_data[key]).strip()

        # 3. Keychain
        services = self.KEYCHAIN_SERVICE_MAP.get(platform.lower(), [platform.lower()])
        for s in services:
            val = self._query_keychain(s)
            if val:
                return val

        return None

    def get_headers_with_cookie(self, platform: str, base_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Attach platform Cookie header if credential exists."""
        headers = dict(base_headers or {})
        cookie = self.get_credential(platform, "cookie")
        if cookie:
            headers["Cookie"] = cookie
        return headers

# Global default instance
credentials_manager = CredentialsManager()
