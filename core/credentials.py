"""
Unified Credential, Browser Cookie Harvest, and Keychain Bridge
"""
import os
import sqlite3
import subprocess
import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml


@contextmanager
def _credential_file_lock(cred_file: Path):
    """Serialize credential read-modify-write cycles across processes."""
    lock_path = cred_file.with_name(cred_file.name + ".lock")
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    with open(fd, "r+b") as lock_file:
        if os.name == "nt":
            import msvcrt
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class CredentialsManager:
    """
    Resolves platform credentials from:
    1. Environment variables (DA_<PLATFORM>_COOKIE)
    2. Local configuration file (config/credentials.yaml)
    3. Live default browser cookies (Chrome, Arc, Edge, Brave, Safari via rookiepy)
    4. Local desktop app SQLite databases (~/Library/Application Support/...)
    5. macOS Keychain
    """

    KEYCHAIN_SERVICE_MAP = {
        "quark": ["quark", "quark-cookie", "grab-cookie", "Quark Safe Storage", "QuarkCloudDrive Safe Storage"],
        "baidu": ["baidu", "baidu-cookie", "grab-cookie", "BaiduNetdisk"],
        "xiaohongshu": ["xiaohongshu", "xhs", "xhs-cookie", "grab-cookie"],
        "bilibili": ["bilibili", "bilibili-sessdata", "grab-cookie"],
    }

    PLATFORM_DOMAINS = {
        "quark": ["quark.cn", "pan.quark.cn"],
        "baidu": ["baidu.com", "pan.baidu.com"],
        "xiaohongshu": ["xiaohongshu.com"],
        "bilibili": ["bilibili.com"],
    }

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(__file__).resolve().parent.parent / "config"
        self.config_dir = config_dir
        self._cached_yaml: Optional[Dict[str, Any]] = None
        self._browser_cookie_cache: Dict[str, str] = {}

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

    def _harvest_from_browsers(self, domains: List[str]) -> Optional[str]:
        """Attempt to extract live cookies from local default browsers via rookiepy."""
        try:
            import rookiepy
            # Try popular browsers in priority order
            browser_loaders = [
                rookiepy.chrome,
                rookiepy.arc,
                rookiepy.edge,
                rookiepy.brave,
                rookiepy.safari,
                rookiepy.firefox,
            ]
            for loader in browser_loaders:
                try:
                    cookies = loader(domains)
                    if cookies:
                        # Assemble into cookie header string
                        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("value"))
                        if cookie_str:
                            return cookie_str
                except Exception:
                    continue
        except ImportError:
            pass
        return None

    def _harvest_from_desktop_apps(self, platform: str) -> Optional[str]:
        """Attempt to harvest cookies from local desktop application profile databases."""
        if platform == "quark":
            cookies: Dict[str, str] = {}
            # 1. Plaintext db
            p_plain = Path.home() / "Library/Application Support/quark-cloud-drive/Cookies"
            if p_plain.exists():
                try:
                    conn = sqlite3.connect(f"file:{p_plain}?mode=ro", uri=True)
                    c = conn.cursor()
                    c.execute("SELECT name, value FROM cookies WHERE host_key LIKE '%quark.cn%' AND value != ''")
                    for name, val in c.fetchall():
                        cookies[name] = val
                    conn.close()
                except Exception:
                    pass

            # 2. Encrypted dbs (QuarkCloudDrive / Quark Default)
            encrypted_dbs = [
                Path.home() / "Library/Application Support/QuarkCloudDrive/Default/Cookies",
                Path.home() / "Library/Application Support/Quark/Default/Cookies",
            ]
            password = None
            try:
                res = subprocess.run(
                    ["/usr/bin/security", "find-generic-password", "-s", "QuarkCloudDrive Safe Storage", "-w"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0 and res.stdout.strip():
                    password = res.stdout.strip().encode("utf-8")
            except Exception:
                pass

            if password:
                try:
                    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                    from cryptography.hazmat.primitives import padding

                    salt = b"saltysalt"
                    key = hashlib.pbkdf2_hmac("sha1", password, salt, 1003, dklen=16)
                    iv = b" " * 16

                    for db in encrypted_dbs:
                        if db.exists():
                            try:
                                conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                                c = conn.cursor()
                                c.execute("SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%quark.cn%'")
                                for name, enc_val in c.fetchall():
                                    if enc_val and enc_val[:3] == b"v10":
                                        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                                        decryptor = cipher.decryptor()
                                        dec = decryptor.update(enc_val[3:]) + decryptor.finalize()
                                        unpadder = padding.PKCS7(128).unpadder()
                                        raw = unpadder.update(dec) + unpadder.finalize()
                                        val = raw[32:].decode("utf-8", errors="ignore") if len(raw) > 32 else raw.decode("utf-8", errors="ignore")
                                        if val:
                                            cookies[name] = val
                                conn.close()
                            except Exception:
                                pass
                except ImportError:
                    pass

            if cookies:
                return "; ".join(f"{k}={v}" for k, v in cookies.items())

        elif platform == "baidu":
            db_path = Path.home() / "Library/Application Support/baidunetdisk/Cookies"
            if db_path.exists():
                try:
                    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                    c = conn.cursor()
                    c.execute("""
                        SELECT name, value FROM cookies 
                        WHERE (host_key LIKE '%baidu.com%' OR host_key LIKE '%baidupcs.com%') 
                          AND value != ''
                    """)
                    items = dict(c.fetchall())
                    conn.close()
                    # Ensure BDUSS is populated from BDUSS_BFESS if missing
                    if "BDUSS" not in items and "BDUSS_BFESS" in items:
                        items["BDUSS"] = items["BDUSS_BFESS"]
                    if items:
                        return "; ".join(f"{k}={v}" for k, v in items.items())
                except Exception:
                    pass

        return None

    def get_credential(self, platform: str, key: str = "cookie") -> Optional[str]:
        """
        Lookup credentials in priority order:
        1. Environment Variable: DA_<PLATFORM>_<KEY>
        2. config/credentials.yaml
        3. Live Browser Cookies (Chrome/Arc/Edge/Safari via rookiepy)
        4. Native Desktop App Cookies SQLite DB (Quark, Baidu)
        5. macOS Keychain
        """
        # 1. Environment Variable
        env_key = f"DA_{platform.upper()}_{key.upper()}"
        if env_key in os.environ and os.environ[env_key].strip():
            return os.environ[env_key].strip()

        # 2. YAML file
        data = self._load_yaml()
        for section in ("pan", "social", "books", "docs", "audio", "dev"):
            if section in data and platform in data[section]:
                plat_data = data[section][platform]
                if isinstance(plat_data, dict) and key in plat_data and plat_data[key]:
                    return str(plat_data[key]).strip()
        if platform in data:
            plat_data = data[platform]
            if isinstance(plat_data, dict) and key in plat_data and plat_data[key]:
                return str(plat_data[key]).strip()

        # 3. Live Browser Cookies
        if key == "cookie":
            if platform in self._browser_cookie_cache:
                return self._browser_cookie_cache[platform]

            domains = self.PLATFORM_DOMAINS.get(platform, [])
            if domains:
                cookie_from_browser = self._harvest_from_browsers(domains)
                if cookie_from_browser:
                    self._browser_cookie_cache[platform] = cookie_from_browser
                    return cookie_from_browser

            # 4. Native Desktop App DBs
            cookie_from_app = self._harvest_from_desktop_apps(platform)
            if cookie_from_app:
                self._browser_cookie_cache[platform] = cookie_from_app
                return cookie_from_app

        # 5. Keychain
        services = self.KEYCHAIN_SERVICE_MAP.get(platform.lower(), [platform.lower()])
        for s in services:
            val = self._query_keychain(s)
            if val:
                return val

        return None

    def save_credential(self, platform: str, cookie: str, section: str = "pan"):
        """Atomically save a credential with 0600 permissions without losing concurrent updates."""
        target_dir = self.config_dir
        cred_file = target_dir / "credentials.yaml"
        target_dir.mkdir(parents=True, exist_ok=True)

        with _credential_file_lock(cred_file):
            # Another process may have updated the file since this manager last read it.
            self._cached_yaml = None
            data = self._load_yaml()
            if section not in data:
                data[section] = {}
            if platform not in data[section]:
                data[section][platform] = {}
            data[section][platform]["cookie"] = cookie

            fd, tmp_name = tempfile.mkstemp(prefix=".credentials.", suffix=".tmp", dir=str(target_dir))
            tmp_file = Path(tmp_name)
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, allow_unicode=True)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_file, cred_file)
                os.chmod(cred_file, 0o600)
            finally:
                tmp_file.unlink(missing_ok=True)

        self._cached_yaml = data
        self._browser_cookie_cache[platform] = cookie

    def get_headers_with_cookie(self, platform: str, base_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Attach platform Cookie header if credential exists."""
        headers = dict(base_headers or {})
        cookie = self.get_credential(platform, "cookie")
        if cookie:
            headers["Cookie"] = cookie
        return headers

# Global default instance
credentials_manager = CredentialsManager()
