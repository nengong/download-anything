"""
Optional browser-assisted sign capture for Baidu Netdisk share downloads.

Baidu's share page signs `/api/sharedownload` in client-side JavaScript. A pure
requests client cannot reproduce that signature, so when Ego Lite is available
we let the real share page produce one request and capture it with CDP.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from core.url_policy import is_http_url

MARKER = "__DA_BAIDU_SHAREDOWNLOAD__"

_SCRIPT = """
const task = await taskSpace("da-baidu-sign-" + Date.now());
const page = task.page("p1");
try {
  await page.goto(%(url)s, { timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.cdp("Network.enable");
  await page.events();
  await page.click('loc=css:button.bottom_download_btn', { label: "下载" });
  await page.waitForTimeout(2500);
  const events = await page.events();
  const hit = events.find(e => {
    if (e.method !== "Network.requestWillBeSent") return false;
    try {
      const u = new URL(e.params.request.url);
      return u.origin === "https://pan.baidu.com" && u.pathname === "/api/sharedownload"
        && !u.username && !u.password && e.params.request.method === "POST";
    } catch (_) { return false; }
  });
  const payload = hit ? {
    url: hit.params.request.url,
    method: hit.params.request.method,
    postData: hit.params.request.postData || "",
  } : null;
  console.log(%(marker)s + JSON.stringify(payload));
} catch (err) {
  console.log(%(marker)s + JSON.stringify({ error: String(err) }));
} finally {
  try { await task.finish({ keep: [] }); } catch (e) {}
}
"""


def valid_capture(data):
    return (isinstance(data, dict)
            and is_http_url(data.get("url"), ("pan.baidu.com",), https_only=True)
            and urlsplit(data["url"]).hostname == "pan.baidu.com"
            and urlsplit(data["url"]).path == "/api/sharedownload"
            and not urlsplit(data["url"]).fragment
            and data.get("method") == "POST"
            and isinstance(data.get("postData"), str) and bool(data["postData"]))


def capture_sharedownload(share_url: str, timeout: int = 90) -> Optional[Dict[str, Any]]:
    """Return {url, method, postData} for a signed Baidu share download request."""
    if not is_http_url(share_url, ("pan.baidu.com", "yun.baidu.com"), https_only=True):
        return None
    if os.getenv("DA_BAIDU_BROWSER", "1").strip() in ("0", "false", "False"):
        return None
    ego = shutil.which("ego-browser")
    if not ego:
        return None

    script = _SCRIPT % {
        "url": json.dumps(share_url),
        "marker": json.dumps(MARKER),
    }
    try:
        proc = subprocess.run(
            [ego, "nodejs"],
            input=script,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except Exception:
        return None

    for line in ((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines():
        if MARKER not in line:
            continue
        raw = line.split(MARKER, 1)[1].strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if valid_capture(data):
            return data
    return None
