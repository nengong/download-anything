"""
Baidu Netdisk (百度网盘) Headless Save-Download-Delete Driver
"""
import json
import re
import time
import uuid
from typing import Optional, List
import requests

from core.baidu_browser import capture_sharedownload, valid_capture
from core.url_policy import is_http_url, scoped_cookies
from http.cookies import SimpleCookie
from core.credentials import credentials_manager
from core.exceptions import ExtractionError, AuthenticationRequiredError, CloudDriveError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class BaiduDriver(BaseDriver):
    """
    Automates Baidu Netdisk micro-asset extraction:
    1. Parse share_id / surl & passcode (提取码).
    2. Silent transfer to temporary folder `/_da_temp/`.
    3. Issue direct high-speed download link via PCS API.
    4. Download asset locally with Range resume.
    5. Cleanup hook: automatically delete remote file from `/_da_temp/`.
    """

    name = "baidu"
    category = "pan"

    SHARE_URL_REGEX = re.compile(r"https?://(?:pan|yun)\.baidu\.com/(?:s/1|share/init\?surl=)([a-zA-Z0-9_-]+)")

    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": "https://pan.baidu.com/",
        "Accept": "application/json, text/plain, */*",
    }

    def can_handle(self, url: str) -> bool:
        return is_http_url(url, ("pan.baidu.com", "yun.baidu.com"), https_only=True)

    def _get_cookie(self) -> str:
        cookie = credentials_manager.get_credential("baidu", "cookie")
        if not cookie:
            raise AuthenticationRequiredError(
                "Baidu Netdisk download requires an authenticated session cookie (BDUSS).\n"
                "Auto-fetch options:\n"
                "  1. Grant Full Disk Access to Terminal in macOS System Settings so da can read Chrome cookies automatically\n"
                "  2. Run `da auth baidu` to log in via browser window with 0 manual copying\n"
                "  3. Set environment variable: export DA_BAIDU_COOKIE='BDUSS=...'"
            )
        return cookie

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        m = self.SHARE_URL_REGEX.match(url) if self.can_handle(url) else None
        if not m:
            raise ExtractionError(f"Invalid Baidu Netdisk share link: {url}")
        surl = m.group(1)
        passcode = (password or "").strip()

        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # 1. Verify Passcode if required
        randsk = ""
        if passcode:
            verify_url = f"https://pan.baidu.com/share/verify?surl={surl}"
            verify_data = {"pwd": passcode, "vcode": "", "vcode_str": ""}
            try:
                vr = session.post(verify_url, data=verify_data, timeout=12)
                v_res = vr.json()
                if v_res.get("errno") == 0:
                    randsk = v_res.get("randsk", "")
                elif v_res.get("errno") == -9:
                    raise ExtractionError("Incorrect Baidu Netdisk 4-digit passcode (提取码错误).")
            except Exception as e:
                if isinstance(e, ExtractionError):
                    raise
                pass

        # 2. Prefer a browser-captured signed share download. Baidu signs
        # `/api/sharedownload` in client-side JS, which requests cannot reproduce.
        if not kwargs.get("inspect_only"):
            captured = capture_sharedownload(url)
            if valid_capture(captured):
                cookie = self._get_cookie()
                session.headers["Cookie"] = cookie
                try:
                    dr = session.post(
                        captured["url"],
                        data=captured.get("postData") or "",
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Referer": url,
                            "X-Requested-With": "XMLHttpRequest",
                        },
                        timeout=20,
                        allow_redirects=False,
                    )
                    direct = dr.json()
                except Exception:
                    direct = {}

                items = direct.get("list") or direct.get("dlink_list") or []
                item = next((x for x in items if x.get("dlink")), None)
                if item:
                    d_filename = item.get("server_filename") or "baidu_download.bin"
                    try:
                        d_size = int(item.get("size")) if item.get("size") else None
                    except (TypeError, ValueError):
                        d_size = None
                    return AssetPackage(
                        title=d_filename,
                        platform=self.name,
                        assets=[TargetAsset(
                            url=item["dlink"],
                            filename=d_filename,
                            file_type="primary",
                            expected_size=d_size,
                            headers={
                                "User-Agent": self.DEFAULT_HEADERS["User-Agent"],
                                "Referer": url,
                            },
                            cookie_jar=scoped_cookies(cookie, "baidu.com"),
                        )],
                        metadata={
                            "original_url": url,
                            "author_name": "Baidu Netdisk User",
                            "filesize_bytes": d_size,
                            "strategy": "browser_share_direct",
                        },
                        raw_markdown=f"百度网盘分享直链: `{d_filename}`",
                    )

        # 3. Get share page details via the current web API (falls back to wxlist)
        cookie = self._get_cookie()
        if randsk:
            values = SimpleCookie()
            values.load(cookie)
            if "BDCLND" in values:
                del values["BDCLND"]
            cookie = "; ".join(f"{k}={v.value}" for k, v in values.items())
            cookie = f"{cookie}; BDCLND={randsk}".lstrip("; ")
        session.headers["Cookie"] = cookie
        bdstoken = ""
        try:
            ls = session.get(
                "https://pan.baidu.com/api/loginStatus?clienttype=0&app_id=250528&web=1",
                timeout=10,
            ).json()
            bdstoken = (ls.get("login_info") or {}).get("bdstoken", "")
        except Exception:
            pass

        list_data = {}
        records = []
        list_url = (
            "https://pan.baidu.com/share/list"
            f"?shorturl={surl}&web=5&app_id=250528&desc=1&showempty=0"
            f"&page=1&num=100&order=time&root=1&view_mode=1"
            f"&channel=chunlei&web=1&bdstoken={bdstoken}&clienttype=0"
        )
        try:
            lr = session.get(list_url, timeout=15)
            list_data = lr.json()
            records = list_data.get("list") or []
        except Exception:
            list_data = {}

        if not records:
            # Legacy fallback for older share pages
            legacy_url = f"https://pan.baidu.com/share/wxlist?channel=weixin&version=2.2.2&op=record&surl={surl}"
            try:
                lr = session.get(legacy_url, timeout=15)
                legacy_data = lr.json()
                if legacy_data.get("errno") == 0:
                    list_data = legacy_data
                    records = (legacy_data.get("data") or {}).get("list") or []
            except Exception:
                pass

        if not records:
            msg = list_data.get("show_msg") or list_data.get("errmsg") or f"errno {list_data.get('errno')}"
            raise CloudDriveError(f"Baidu share access error: {msg}")

        target_file = records[0]
        fs_id = target_file.get("fs_id")
        filename = target_file.get("server_filename", "baidu_download.bin")
        filesize = target_file.get("size")
        try:
            filesize = int(filesize) if filesize is not None else None
        except (TypeError, ValueError):
            filesize = None
        share_id = (
            list_data.get("share_id")
            or (list_data.get("data") or {}).get("shareid")
            or target_file.get("share_id")
        )
        uk = (
            list_data.get("uk")
            or (list_data.get("data") or {}).get("uk")
            or target_file.get("uk")
        )

        if kwargs.get("inspect_only"):
            return AssetPackage(title=filename, platform=self.name, assets=[TargetAsset(
                url="", filename=filename, expected_size=filesize,
            )], metadata={"original_url": url, "requires_transfer": True,
                         "direct_url_available": False})

        # 3. Requires BDUSS for Silent Transfer & PCS direct link download
        user_headers = dict(self.DEFAULT_HEADERS)
        user_headers["Cookie"] = cookie

        temp_path = "/_da_temp_" + uuid.uuid4().hex
        self._create_temp_folder(session, user_headers, temp_path, bdstoken)

        owned_package = AssetPackage(title=filename, platform=self.name, context={"owned_temp_path": temp_path, "headers": user_headers, "bdstoken": bdstoken})
        try:
            # Ensure temp directory `/_da_temp/` exists
            # Execute silent transfer
            transfer_url = (
                "https://pan.baidu.com/share/transfer"
                f"?shareid={share_id}&from={uk}&channel=chunlei&web=1"
                f"&app_id=250528&clienttype=0&bdstoken={bdstoken}"
            )
            transfer_payload = {
                "fsidlist": f"[{fs_id}]",
                "path": temp_path
            }
            try:
                tr = session.post(transfer_url, data=transfer_payload, headers=user_headers, timeout=15)
                t_res = tr.json()
            except Exception as e:
                raise CloudDriveError(f"Failed to transfer file to Baidu temp folder: {e}")

            if t_res.get("errno") != 0:
                if t_res.get("errno") == -8:
                    # Unexpected existing content must never be deleted by this task.
                    owned_package.context.clear()
                raise CloudDriveError(f"Baidu silent transfer failed: {t_res.get('show_msg', t_res.get('errmsg'))}")

            # 4. Query new file metadata & obtain direct PCS download link (dlink)
            dlink = self._get_dlink(session, user_headers, filename, temp_path, bdstoken)
            if not dlink:
                raise CloudDriveError(f"Failed to resolve PCS direct download link for `{filename}`.")

            primary_asset = TargetAsset(
                url=dlink,
                filename=filename,
                file_type="primary",
                expected_size=filesize,
                headers={
                    "User-Agent": "pan.baidu.com",
                },
                cookie_jar=scoped_cookies(cookie, "baidu.com"),
            )

            return AssetPackage(
                title=filename,
                platform=self.name,
                assets=[primary_asset],
                metadata={
                    "original_url": url,
                    "author_name": "Baidu Netdisk User",
                    "filesize_bytes": filesize,
                    "share_id": share_id,
                },
                context={
                    "headers": user_headers,
                    "filename": filename,
                    "owned_temp_path": temp_path,
                    "bdstoken": bdstoken,
                },
                raw_markdown=f"百度网盘无感穿透解析文件: `{filename}`"
            )
        except BaseException as exc:
            self.cleanup_after_error(owned_package, exc)
            raise

    def _create_temp_folder(self, session: requests.Session, headers: dict, temp_path: str, bdstoken: str):
        create_url = (
            "https://pan.baidu.com/api/create"
            f"?a=commit&channel=chunlei&web=1&app_id=250528&clienttype=0&bdstoken={bdstoken}"
        )
        payload = {"path": temp_path, "isdir": 1, "size": 0, "block_list": "[]"}
        response = session.post(create_url, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
        if response.json().get("errno") != 0:
            raise CloudDriveError("Baidu refused creation of an owned temporary directory")

    def _get_dlink(self, session: requests.Session, headers: dict, filename: str, temp_path: str,
                   bdstoken: str) -> Optional[str]:
        """Resolve a direct PCS dlink for the transferred file."""
        target = f"{temp_path}/{filename}"
        try:
            r = session.get(
                "https://pan.baidu.com/api/filemetas",
                params={"dlink": 1, "target": json.dumps([target]), "web": 1,
                        "app_id": 250528, "clienttype": 0, "bdstoken": bdstoken},
                headers=headers,
                timeout=15,
            )
            data = r.json()
            for item in data.get("info", []):
                if item.get("dlink"):
                    return item["dlink"]
        except Exception:
            pass

        # Fallback: list the temp folder, then query filemetas by fs_id
        try:
            r = session.get(
                "https://pan.baidu.com/api/list",
                params={"dir": temp_path, "num": 50, "order": "time", "desc": 1,
                        "web": 1, "app_id": 250528, "clienttype": 0, "bdstoken": bdstoken},
                headers=headers,
                timeout=10,
            )
            data = r.json()
            fs_id = next((item.get("fs_id") for item in data.get("list", [])
                          if item.get("server_filename") == filename), None)
            if fs_id:
                r2 = session.get(
                    "https://pan.baidu.com/rest/2.0/xpan/multimedia",
                    params={"method": "filemetas", "dlink": 1, "fsids": json.dumps([fs_id]),
                            "web": 1, "app_id": 250528, "clienttype": 0, "bdstoken": bdstoken},
                    headers=headers,
                    timeout=15,
                )
                for item in r2.json().get("list", []):
                    if item.get("dlink"):
                        return item["dlink"]
        except Exception:
            pass
        return None

    def cleanup(self, package: AssetPackage) -> None:
        """Post-download atomic cleanup: delete the file from `/_da_temp/`."""
        temp_path = package.context.get("owned_temp_path")
        headers = package.context.get("headers")
        bdstoken = package.context.get("bdstoken", "")
        if not temp_path or not re.fullmatch(r"/_da_temp_[a-f0-9]{32}", temp_path) or not headers:
            return

        del_url = (
            "https://pan.baidu.com/rest/2.0/xpan/file?method=filemanager&opera=delete"
            f"&async=2&channel=chunlei&web=1&app_id=250528&clienttype=0&bdstoken={bdstoken}"
        )
        payload = {"filelist": json.dumps([temp_path])}
        response = requests.post(del_url, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
        if response.json().get("errno") != 0:
            raise CloudDriveError("Baidu temporary directory cleanup was not confirmed")
