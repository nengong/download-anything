"""
Resilient Streaming Download Engine with Range Support, Size Guards, and Curl Failover
"""
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Dict
import requests

from core.exceptions import DownloadError, FileTooLargeError

DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # 500 MB
DEFAULT_CHUNK_SIZE = 65536            # 64 KB
DEFAULT_INACTIVITY_TIMEOUT = 30       # seconds

@dataclass
class FetcherOptions:
    max_bytes: int = DEFAULT_MAX_BYTES
    chunk_size: int = DEFAULT_CHUNK_SIZE
    inactivity_timeout: int = DEFAULT_INACTIVITY_TIMEOUT
    max_retries: int = 3
    headers: Optional[Dict[str, str]] = None

class Fetcher:
    """Robust streaming download engine preventing premature cutoffs and memory bloat."""

    def __init__(self, options: Optional[FetcherOptions] = None):
        self.options = options or FetcherOptions()

    def download(
        self,
        url: str,
        dest_path: Path,
        headers: Optional[Dict[str, str]] = None,
        expected_size: Optional[int] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None
    ) -> int:
        """
        Download remote stream to dest_path with resume support, size guard,
        and automatic curl failover for tough CDN endpoints.
        Supports data: and file: URIs seamlessly.
        Returns total bytes downloaded.
        """
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle data: URI directly
        if url.startswith("data:"):
            import base64
            import urllib.parse
            header, encoded = url.split(",", 1) if "," in url else ("", "")
            if ";base64" in header:
                content = base64.b64decode(encoded)
            else:
                content = urllib.parse.unquote_to_bytes(encoded)
            dest_path.write_bytes(content)
            if progress_callback:
                progress_callback(len(content), len(content))
            return len(content)

        part_path = dest_path.with_suffix(dest_path.suffix + ".part")

        req_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        }
        if self.options.headers:
            req_headers.update(self.options.headers)
        if headers:
            req_headers.update(headers)

        existing_bytes = 0
        if part_path.exists():
            existing_bytes = part_path.stat().st_size
            if existing_bytes > self.options.max_bytes:
                part_path.unlink(missing_ok=True)
                existing_bytes = 0

        # Attempt download with requests first
        active_url = url
        last_error = None
        for attempt in range(1, self.options.max_retries + 1):
            try:
                attempt_headers = dict(req_headers)
                if existing_bytes > 0:
                    attempt_headers["Range"] = f"bytes={existing_bytes}-"

                with requests.get(
                    active_url,
                    headers=attempt_headers,
                    stream=True,
                    timeout=(15, self.options.inactivity_timeout),
                    allow_redirects=True
                ) as resp:
                    if resp.status_code == 416:  # Range Not Satisfiable -> file already complete
                        part_path.replace(dest_path)
                        return dest_path.stat().st_size

                    resp.raise_for_status()

                    # Determine remote total size
                    remote_len = None
                    content_length = resp.headers.get("Content-Length")
                    if content_length and content_length.isdigit():
                        cl = int(content_length)
                        if resp.status_code == 206:  # Partial Content
                            remote_len = existing_bytes + cl
                        else:
                            remote_len = cl
                            existing_bytes = 0

                    total_expected = remote_len or expected_size

                    # Enforce pre-download size guard
                    if total_expected and total_expected > self.options.max_bytes:
                        if part_path.exists():
                            part_path.unlink(missing_ok=True)
                        raise FileTooLargeError(
                            f"Asset size ({total_expected / (1024*1024):.1f}MB) exceeds "
                            f"maximum allowed limit ({self.options.max_bytes / (1024*1024):.1f}MB)"
                        )

                    # Stream write to part file
                    mode = "ab" if existing_bytes > 0 and resp.status_code == 206 else "wb"
                    current_bytes = existing_bytes if mode == "ab" else 0

                    with open(part_path, mode) as f:
                        for chunk in resp.iter_content(chunk_size=self.options.chunk_size):
                            if not chunk:
                                continue
                            f.write(chunk)
                            current_bytes += len(chunk)

                            # Enforce live download size guard
                            if current_bytes > self.options.max_bytes:
                                f.flush()
                                part_path.unlink(missing_ok=True)
                                raise FileTooLargeError(
                                    f"Download exceeded maximum size threshold "
                                    f"({self.options.max_bytes / (1024*1024):.1f}MB)"
                                )

                            if progress_callback:
                                progress_callback(current_bytes, total_expected)

                    # Completed stream successfully
                    if part_path.exists() and part_path.stat().st_size > 0:
                        part_path.replace(dest_path)
                        return dest_path.stat().st_size

            except FileTooLargeError:
                raise
            except Exception as e:
                last_error = e
                # Check for domestic mirror failover when foreign link times out
                try:
                    from core.mirror_router import MirrorRouter
                    candidate_mirrors = MirrorRouter.get_mirrors(url)
                    if candidate_mirrors and attempt <= len(candidate_mirrors):
                        active_url = candidate_mirrors[attempt - 1]
                        if part_path.exists():
                            part_path.unlink(missing_ok=True)
                            existing_bytes = 0
                    else:
                        if part_path.exists():
                            existing_bytes = part_path.stat().st_size
                except Exception:
                    if part_path.exists():
                        existing_bytes = part_path.stat().st_size
                time.sleep(1.0 * attempt)

        # 2. Seamless failover to native curl if requests struggled
        curl_success = self._download_via_curl(url, part_path, dest_path, req_headers, progress_callback)
        if curl_success:
            return dest_path.stat().st_size

        # Retries exhausted
        if part_path.exists() and part_path.stat().st_size == 0:
            part_path.unlink(missing_ok=True)
        raise DownloadError(f"Download failed after {self.options.max_retries} attempts: {last_error}")

    def _download_via_curl(
        self,
        url: str,
        part_path: Path,
        dest_path: Path,
        headers: Dict[str, str],
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None
    ) -> bool:
        """Secondary transfer engine using curl with auto-resume and HTTP/1.1+HTTP/2."""
        try:
            cmd = ["curl", "-C", "-", "-sSL", "--connect-timeout", "15"]
            for k, v in headers.items():
                if k.lower() == "referer":
                    cmd.extend(["-e", v])
                elif k.lower() == "user-agent":
                    cmd.extend(["-A", v])
                else:
                    cmd.extend(["-H", f"{k}: {v}"])
            cmd.extend([url, "-o", str(part_path)])

            proc = subprocess.Popen(cmd)
            while proc.poll() is None:
                if part_path.exists():
                    cur_size = part_path.stat().st_size
                    if cur_size > self.options.max_bytes:
                        proc.kill()
                        part_path.unlink(missing_ok=True)
                        raise FileTooLargeError(f"Download exceeded {self.options.max_bytes / (1024*1024):.1f}MB")
                    if progress_callback:
                        progress_callback(cur_size, None)
                time.sleep(0.5)

            if proc.returncode == 0 and part_path.exists() and part_path.stat().st_size > 0:
                part_path.replace(dest_path)
                return True
        except FileTooLargeError:
            raise
        except Exception:
            pass
        return False
