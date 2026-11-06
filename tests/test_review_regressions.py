"""Observable regressions for the 18-issue review. All accounts/backends are fake."""
import base64
import io
import json
import subprocess
import sys
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import zipfile

import pytest
import requests
from PIL import Image

from cli import process_download
from core.baidu_browser import capture_sharedownload, valid_capture, MARKER
from core.exceptions import DownloadError, ExtractionError
from core.fetcher import Fetcher, FetcherOptions
from core.index_db import AssetIndexDB
from core.url_policy import is_http_url, scoped_cookies
from core.verifier import Verifier
from drivers.base import AssetPackage, BaseDriver, TargetAsset
from drivers.docs.wechat import WeChatDriver
from drivers.docs.web_article import WebArticleDriver
from drivers.docs.feishu import FeishuDocDriver
from drivers.docs.notion import NotionPublicDriver
from drivers.pan.baidu import BaiduDriver
from drivers.social.bilibili import BilibiliDriver
from drivers.social.instagram import InstagramDriver
from drivers.social.weibo import WeiboDriver
from drivers.social.ytdlp_fallback import YtDlpFallbackDriver


@pytest.fixture(autouse=True)
def isolated_delivery(monkeypatch, tmp_path):
    monkeypatch.setattr(AssetIndexDB, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(AssetIndexDB, "DB_PATH", tmp_path / "db/index.db")
    for name in ("OBSIDIAN_VAULT_PATH", "DA_VAULT_PATH", "DA_OUTPUT_DIR"):
        monkeypatch.delenv(name, raising=False)


def response(url, payload, status=200):
    r = requests.Response()
    r.url, r.status_code, r.encoding = url, status, "utf-8"
    r._content, r._content_consumed = payload, True
    r.headers["Content-Length"] = str(len(payload))
    return r


def image_bytes(color="red"):
    out = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(out, format="PNG")
    return out.getvalue()


def data_asset(name, payload, role="primary"):
    return TargetAsset("data:application/octet-stream;base64," + base64.b64encode(payload).decode(), name, role)


class StubDriver(BaseDriver):
    def __init__(self, package): self.package = package
    def can_handle(self, url): return True
    def extract(self, url, **kwargs): return self.package


def run_package(package, out=None, **options):
    with patch("cli.get_default_drivers", return_value=[StubDriver(package)]):
        return process_download("https://example.invalid/test", output_dir=str(out) if out else None,
                                agent_mode=True, **options)


@pytest.mark.parametrize("url", [
    "https://attacker.invalid/b23.tv/BV1xx411c7mD",
    "https://b23.tv.attacker.invalid/BV1xx411c7mD",
    "https://b23.tv@attacker.invalid/BV1xx411c7mD",
    "https://attacker.invalid/?next=https://pan.baidu.com/s/1demo",
])
def test_spoofed_platform_links_never_read_credentials_or_send_requests(url):
    driver = BaiduDriver() if "pan.baidu.com" in url else BilibiliDriver()
    with patch("core.credentials.credentials_manager.get_credential") as credential, \
         patch.object(requests.Session, "get") as get, patch.object(requests.Session, "post") as post:
        assert not driver.can_handle(url)
        with pytest.raises(ExtractionError): driver.extract(url)
    credential.assert_not_called()
    get.assert_not_called()
    post.assert_not_called()


def prepared_cookie(jar, url):
    return requests.Session().prepare_request(requests.Request("GET", url, cookies=jar)).headers.get("Cookie", "")


def test_bilibili_cookie_stays_on_secure_platform_api():
    jar = scoped_cookies("SESSDATA=FAKE", "bilibili.com")
    assert "SESSDATA=FAKE" in prepared_cookie(jar, "https://api.bilibili.com/x")
    for url in ("https://b23.tv/x", "https://evil.invalid/", "http://api.bilibili.com/x",
                "https://bilibili.com.evil.invalid/x"):
        assert not prepared_cookie(jar, url)


@pytest.mark.parametrize("mutation", [
    {"url": "https://evil.invalid/api/sharedownload"},
    {"url": "https://pan.baidu.com.evil.invalid/api/sharedownload"},
    {"url": "http://pan.baidu.com/api/sharedownload"},
    {"url": "https://pan.baidu.com/api/sharedownload/extra"},
    {"url": "https://sub.pan.baidu.com/api/sharedownload"},
    {"url": "https://evil@pan.baidu.com/api/sharedownload"},
    {"method": "GET"}, {"postData": ""},
])
def test_capture_origin_method_and_body_are_checked_at_both_boundaries(monkeypatch, mutation):
    captured = {"url": "https://pan.baidu.com/api/sharedownload?sign=FAKE", "method": "POST", "postData": "fid=1", **mutation}
    assert not valid_capture(captured)
    monkeypatch.setenv("DA_BAIDU_BROWSER", "1")
    proc = SimpleNamespace(stdout=MARKER + json.dumps(captured), stderr="")
    with patch("core.baidu_browser.shutil.which", return_value="/fake/ego"), \
         patch("core.baidu_browser.subprocess.run", return_value=proc):
        assert capture_sharedownload("https://pan.baidu.com/s/1demo") is None
    with patch("drivers.pan.baidu.capture_sharedownload", return_value=captured), \
         patch.object(BaiduDriver, "_get_cookie", side_effect=RuntimeError("stop before API")), \
         patch.object(requests.Session, "post") as post:
        with pytest.raises(RuntimeError, match="stop before API"):
            BaiduDriver().extract("https://pan.baidu.com/s/1demo")
    post.assert_not_called()


def test_valid_browser_capture_is_testable_and_replay_cannot_redirect(monkeypatch):
    captured = {"url": "https://pan.baidu.com/api/sharedownload?sign=FAKE", "method": "POST", "postData": "fid=1"}
    monkeypatch.setenv("DA_BAIDU_BROWSER", "1")
    proc = SimpleNamespace(stdout=MARKER + json.dumps(captured), stderr="")
    with patch("core.baidu_browser.shutil.which", return_value="/fake/ego"), \
         patch("core.baidu_browser.subprocess.run", return_value=proc):
        assert capture_sharedownload("https://pan.baidu.com/s/1demo") == captured
    result = {"list": [{"server_filename": "f.bin", "dlink": "https://cdn.invalid/f.bin"}]}
    with patch("drivers.pan.baidu.capture_sharedownload", return_value=captured), \
         patch.object(BaiduDriver, "_get_cookie", return_value="BDUSS=FAKE"), \
         patch.object(requests.Session, "post", return_value=SimpleNamespace(json=lambda: result)) as post:
        package = BaiduDriver().extract("https://pan.baidu.com/s/1demo")
    assert post.call_args.kwargs["allow_redirects"] is False
    assert "Cookie" not in package.primary_asset.headers
    assert not prepared_cookie(package.primary_asset.cookie_jar, package.primary_asset.url)


def scoped_test_jar():
    jar = CookieJar()
    jar.set_cookie(Cookie(0, "PRIVATE", "FAKE", None, False, ".origin.invalid", True, True,
                          "/private", True, True, None, True, None, None, {}, False))
    return jar


def test_ytdlp_cookies_retain_domain_path_secure_for_every_asset(monkeypatch):
    info = {"title": "probe", "url": "https://media.invalid/file.mp4", "ext": "mp4",
            "thumbnail": "https://image.invalid/c.png",
            "subtitles": {"en": [{"url": "https://sub.invalid/a.vtt", "ext": "vtt"}]},
            "http_headers": {"Cookie": "UNSCOPED=FAKE", "Authorization": "FAKE"}}
    backend = MagicMock()
    backend.__enter__.return_value = backend
    backend.extract_info.return_value = info
    backend.cookiejar = scoped_test_jar()
    monkeypatch.setattr("yt_dlp.YoutubeDL", lambda options: backend)
    package = YtDlpFallbackDriver().extract("https://origin.invalid/private/watch")
    assert len(package.assets) == 3
    for asset in package.assets:
        assert not any(k.lower() in {"cookie", "authorization"} for k in asset.headers)
        assert not prepared_cookie(asset.cookie_jar, asset.url)
        assert "PRIVATE=FAKE" in prepared_cookie(asset.cookie_jar, "https://origin.invalid/private/ok")
        assert not prepared_cookie(asset.cookie_jar, "https://origin.invalid/public/denied")
        assert not prepared_cookie(asset.cookie_jar, "http://origin.invalid/private/denied")


def test_scoped_cookie_survives_native_download_without_broad_headers(monkeypatch, tmp_path):
    instances = []
    class FakeYDL:
        def __init__(self, options):
            self.options, self.cookiejar = options, CookieJar()
            instances.append(self)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def download(self, urls):
            Path(self.options["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(b"fake")
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    asset = TargetAsset("https://origin.invalid/private/watch", "a.mp4", cookie_jar=scoped_test_jar())
    YtDlpFallbackDriver().download_primary(asset, tmp_path / "a.mp4", 1024)
    jar = instances[0].cookiejar
    assert "PRIVATE=FAKE" in prepared_cookie(jar, "https://origin.invalid/private/media")
    assert not prepared_cookie(jar, "https://other.invalid/private/media")
    assert "http_headers" not in instances[0].options


@pytest.mark.parametrize("error", ["There is no video in this post"])
def test_instagram_actual_single_photo_error_reaches_gallery(monkeypatch, error):
    backend = MagicMock()
    backend.__enter__.return_value = backend
    backend.extract_info.side_effect = Exception(error)
    monkeypatch.setattr("yt_dlp.YoutubeDL", lambda opts: backend)
    with patch.object(InstagramDriver, "_extract_photos", return_value="PHOTOS") as photos:
        assert InstagramDriver().extract("https://instagram.com/p/ABC/") == "PHOTOS"
    photos.assert_called_once_with("https://www.instagram.com/p/ABC/", "ABC")


def test_instagram_raw_photo_carousel_reaches_validated_gallery(monkeypatch):
    # Shape from the installed extractor's _extract_product output, before yt-dlp format processing.
    backend = MagicMock()
    backend.__enter__.return_value = backend
    backend.extract_info.return_value = {"_type": "playlist", "entries": [
        {"id": "1", "formats": [], "thumbnails": [{"url": "https://cdn.invalid/a.jpg"}]},
        {"id": "2", "formats": [], "thumbnails": [{"url": "https://cdn.invalid/b.jpg"}]},
    ]}
    monkeypatch.setattr("yt_dlp.YoutubeDL", lambda opts: backend)
    with patch.object(InstagramDriver, "_extract_photos", return_value="PHOTOS"):
        assert InstagramDriver().extract("https://instagram.com/p/ABC/") == "PHOTOS"


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired("gallery", 60), OSError("missing"), None])
def test_weibo_ordinary_gallery_failures_allow_video(monkeypatch, failure):
    monkeypatch.setattr(requests.Session, "get", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"ok": 0}))
    run = MagicMock(return_value=SimpleNamespace(returncode=1, stderr="No module named gallery_dl"))
    if failure: run.side_effect = failure
    monkeypatch.setattr("drivers.social.weibo.subprocess.run", run)
    backend = MagicMock()
    backend.__enter__.return_value = backend
    backend.extract_info.return_value = {"title": "Video", "url": "https://cdn.invalid/media.mp4"}
    monkeypatch.setattr("yt_dlp.YoutubeDL", lambda opts: backend)
    package = WeiboDriver().extract("https://weibo.com/123/ABC")
    assert package.primary_asset.url == "https://cdn.invalid/media.mp4"
    backend.extract_info.assert_called_once()


@pytest.mark.parametrize("initial", ["BDUSS=FAKE", "BDUSS=FAKE; BDCLND=OLD"])
def test_baidu_transfer_and_normal_cleanup_share_current_context(monkeypatch, initial, tmp_path):
    from core.url_policy import scoped_cookies
    observed = {}
    def get(session, url, **kwargs):
        if "loginStatus" in url: return SimpleNamespace(json=lambda: {"login_info": {"bdstoken": "TOKEN"}})
        if "/share/list" in url:
            observed["list_cookie"] = session.headers["Cookie"]
            return SimpleNamespace(json=lambda: {"list": [{"fs_id": 1, "server_filename": "f.txt", "size": 1}], "share_id": 2, "uk": 3})
        raise AssertionError(url)
    def post(session, url, **kwargs):
        if "/share/verify" in url: return SimpleNamespace(json=lambda: {"errno": 0, "randsk": "NEW"})
        observed["transfer_cookie"] = kwargs["headers"]["Cookie"]
        return SimpleNamespace(json=lambda: {"errno": 0})
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "post", post)
    monkeypatch.setattr(BaiduDriver, "_get_cookie", lambda self: initial)
    monkeypatch.setattr(BaiduDriver, "_create_temp_folder", lambda *a: None)
    monkeypatch.setattr(BaiduDriver, "_get_dlink", lambda *a: "data:text/plain,x")
    monkeypatch.setattr("drivers.pan.baidu.capture_sharedownload", lambda url: None)
    driver = BaiduDriver()
    with patch("drivers.pan.baidu.requests.post", return_value=SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"errno": 0})) as delete, \
         patch("cli.get_default_drivers", return_value=[driver]):
        result = process_download("https://pan.baidu.com/s/1demo", password="abcd", output_dir=str(tmp_path), agent_mode=True)
    assert result["status"] == "success"
    for cookie in observed.values():
        assert "BDCLND=NEW" in cookie and "BDCLND=OLD" not in cookie
    assert "bdstoken=TOKEN" in delete.call_args.args[0]
    assert result["operations"]["cleanup"]["status"] == "success"


@pytest.mark.parametrize("missing", [False, True])
def test_epub_accepts_image_chapter_but_requires_image_resource(tmp_path, epub_members, missing):
    opf = epub_members["OEBPS/book.opf"].replace(b"</manifest>", b'<item id="image" href="pic.png" media-type="image/png"/></manifest>')
    epub_members["OEBPS/book.opf"] = opf
    epub_members["OEBPS/text/chapter.xhtml"] = b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Scan</title></head><body><img src="../pic.png"/></body></html>'
    if not missing: epub_members["OEBPS/pic.png"] = image_bytes()
    path = tmp_path / "scan.epub"
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in epub_members.items(): archive.writestr(name, payload)
    verified = Verifier.verify(path)
    assert verified.valid is not missing, verified.error_message
    if missing: assert "manifest resource" in verified.error_message


@pytest.mark.parametrize("driver,url,html", [
    (WeChatDriver, "https://mp.weixin.qq.com/s/probe", '<h1 id="activity-name">Probe</h1><div id="js_content"><img data-src="{src}" data-type="txt"/></div>'),
    (WebArticleDriver, "https://medium.com/probe", '<title>Probe</title><article><img src="{src}"/></article>'),
    (FeishuDocDriver, "https://demo.feishu.cn/docx/probe", '<title>Probe</title><main><img src="{src}"/></main>'),
    (NotionPublicDriver, "https://demo.notion.site/probe", '<title>Probe</title><main><img src="{src}"/></main>'),
])
def test_remote_document_cannot_copy_local_file(monkeypatch, tmp_path, driver, url, html):
    private = tmp_path / "private.txt"
    private.write_text("PRIVATE_FAKE")
    page = html.format(src=private.as_uri()).encode()
    monkeypatch.setattr(requests.Session, "get", lambda *a, **kw: response(url, page))
    with pytest.raises(ExtractionError, match="HTTP"):
        driver().extract(url)
    assert list(tmp_path.iterdir()) == [private]


def test_fetcher_local_access_requires_matching_explicit_source(tmp_path):
    source = tmp_path / "local.txt"
    source.write_text("explicit")
    dest = tmp_path / "out.txt"
    with pytest.raises(DownloadError, match="explicit local source"):
        Fetcher().download(source.as_uri(), dest)
    with pytest.raises(DownloadError):
        Fetcher().download(source.as_uri(), dest, local_source=tmp_path / "other.txt")
    Fetcher().download(source.as_uri(), dest, local_source=source)
    assert dest.read_text() == "explicit"


def test_two_photos_with_title_matching_second_filename_remain_distinct(tmp_path):
    first, second = image_bytes("red"), image_bytes("blue")
    package = AssetPackage("image_02", "twitter", assets=[data_asset("content.png", first), data_asset("image_02.png", second, "companion")])
    result = run_package(package, tmp_path)
    assert result["status"] == "success"
    assert Path(result["primary_asset"]).read_bytes() == first
    assert len(result["companion_files"]) == 1
    assert Path(result["companion_files"][0]).read_bytes() == second
    assert result["primary_asset"] != result["companion_files"][0]


def test_previous_delivery_is_never_overwritten(tmp_path):
    first = run_package(AssetPackage("same", "test", assets=[data_asset("content.txt", b"first")]), tmp_path)
    second = run_package(AssetPackage("same", "test", assets=[data_asset("content.txt", b"second")]), tmp_path)
    assert first["output_dir"] != second["output_dir"]
    assert Path(first["primary_asset"]).read_bytes() == b"first"
    assert Path(second["primary_asset"]).read_bytes() == b"second"


@pytest.mark.parametrize("driver,url", [(WebArticleDriver, "https://medium.com/probe"), (FeishuDocDriver, "https://demo.feishu.cn/docx/probe"), (NotionPublicDriver, "https://demo.notion.site/probe")])
def test_document_image_links_survive_full_pipeline(monkeypatch, tmp_path, driver, url):
    page = '<html><title>Doc</title><main><article><p>Body</p><img src="/image.png"/></article></main></html>'
    monkeypatch.setattr(requests.Session, "get", lambda *a, **kw: response(url, page.encode()))
    monkeypatch.setattr(requests, "get", lambda u, **kw: response(u, image_bytes()))
    with patch("cli.get_default_drivers", return_value=[driver()]):
        result = process_download(url, output_dir=str(tmp_path), agent_mode=True)
    primary = Path(result["primary_asset"])
    text = primary.read_text(encoding="utf-8")
    import re
    links = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text)
    assert links
    assert all((primary.parent / link).is_file() for link in links)
    assert result["status"] == "success"


@pytest.mark.parametrize("driver,url", [(WebArticleDriver, "https://medium.com/probe"), (FeishuDocDriver, "https://demo.feishu.cn/docx/probe"), (NotionPublicDriver, "https://demo.notion.site/probe")])
@pytest.mark.parametrize("status", [404, 429, 500])
def test_document_http_error_never_becomes_success(monkeypatch, driver, url, status):
    monkeypatch.setattr(requests.Session, "get", lambda *a, **kw: response(url, b"<html>Failed</html>", status))
    with pytest.raises(ExtractionError): driver().extract(url)


def archive_package():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive: archive.writestr("inside.txt", "inside")
    return AssetPackage("Cache", "test", assets=[data_asset("archive.zip", out.getvalue())])


def test_cache_options_and_environment_directory_are_respected(monkeypatch, tmp_path):
    monkeypatch.setattr("cli.resolve_output_directory", lambda *a, **kw: tmp_path / "delivery")
    first = run_package(archive_package(), auto_unzip=False)
    second = run_package(archive_package(), auto_unzip=True)
    assert second["status"] == "success" and second["extracted_files"]
    assert first["extracted_files"] == []
    cached = run_package(archive_package(), auto_unzip=True)
    assert cached["status"] == "cached"
    monkeypatch.setenv("DA_OUTPUT_DIR", str(tmp_path / "new-output"))
    # Remove only the resolver stub so the real environment-directory path is used.
    from core.path_resolver import resolve_output_directory
    monkeypatch.setattr("cli.resolve_output_directory", resolve_output_directory)
    changed = run_package(archive_package())
    assert changed["status"] == "success"
    assert Path(changed["output_dir"]).is_relative_to(tmp_path / "new-output")


def test_missing_companion_invalidates_complete_delivery_cache(monkeypatch, tmp_path):
    monkeypatch.setattr("cli.resolve_output_directory", lambda *a, **kw: tmp_path / "delivery")
    package = lambda: AssetPackage("Files", "test", assets=[data_asset("one.txt", b"1"), data_asset("two.txt", b"2", "companion")])
    first = run_package(package())
    assert run_package(package())["status"] == "cached"
    Path(first["companion_files"][0]).unlink()
    assert run_package(package())["status"] == "success"


def test_real_ytdlp_playlist_dispatch_is_blocked_before_media_transfer(monkeypatch, tmp_path):
    import yt_dlp
    from yt_dlp.extractor.common import InfoExtractor
    class OfflinePlaylistIE(InfoExtractor):
        _VALID_URL = r'https://playlist\.invalid/(?P<id>demo)'
        def _real_extract(self, url):
            return self.playlist_result([
                self.url_result('https://item.invalid/1', OfflineItemIE),
                self.url_result('https://item.invalid/2', OfflineItemIE),
            ], playlist_id='demo')
    class OfflineItemIE(InfoExtractor):
        _VALID_URL = r'https://item\.invalid/(?P<id>[12])'
        def _real_extract(self, url):
            item = self._match_id(url)
            return {'id': item, 'title': 'Item ' + item, 'formats': [{
                'url': 'https://cdn.invalid/' + item + '.m3u8',
                'protocol': 'm3u8_native', 'ext': 'mp4', 'vcodec': 'h264', 'acodec': 'aac',
            }]}
    transferred = []
    class OfflineYDL(yt_dlp.YoutubeDL):
        def __init__(self, params):
            super().__init__(params, auto_init=False)
            self.add_info_extractor(OfflinePlaylistIE())
            self.add_info_extractor(OfflineItemIE())
        def process_info(self, info):
            transferred.append(info['id'])
            Path(self.prepare_filename(info)).write_bytes(b'fake media')
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', OfflineYDL)
    driver = YtDlpFallbackDriver()
    with pytest.raises(ExtractionError, match='single video/audio'):
        driver.extract('https://playlist.invalid/demo')
    asset = TargetAsset('https://playlist.invalid/demo', 'out.mp4', download_strategy='ytdlp')
    with pytest.raises(DownloadError, match='Playlist'):
        driver.download_primary(asset, tmp_path / 'out.mp4', 1024)
    assert transferred == []
    assert list(tmp_path.iterdir()) == []


def test_scoped_fetcher_cookie_is_not_replayed_across_redirect(monkeypatch, tmp_path):
    from requests.adapters import BaseAdapter
    seen = []
    class Adapter(BaseAdapter):
        def send(self, request, **kwargs):
            seen.append((request.url, request.headers.get('Cookie', '')))
            result = response(request.url, b'final')
            result.request, result.raw = request, io.BytesIO(b'final')
            if len(seen) == 1:
                result.status_code = 302
                result.headers['Location'] = 'https://evil.invalid/private/end'
            return result
        def close(self): pass
    session = requests.Session()
    session.mount('https://', Adapter())
    def fake_get(url, **kwargs):
        request = requests.Request('GET', url, headers=kwargs.get('headers'), cookies=kwargs.get('cookies'))
        return session.send(session.prepare_request(request), stream=True, allow_redirects=True)
    monkeypatch.setattr(requests, 'get', fake_get)
    target = tmp_path / 'out.txt'
    Fetcher().download('https://origin.invalid/private/start', target, cookie_jar=scoped_test_jar())
    assert seen[0][1] == 'PRIVATE=FAKE'
    assert seen[1] == ('https://evil.invalid/private/end', '')
    assert target.read_bytes() == b'final'


def test_curl_fallback_uses_scoped_cookie_file_and_removes_it(monkeypatch, tmp_path):
    from http.cookiejar import MozillaCookieJar
    observed = {}
    part, dest = tmp_path / 'out.part', tmp_path / 'out.bin'
    def launch(command, **kwargs):
        cookie_path = Path(command[command.index('--cookie') + 1])
        observed['cookie_path'] = cookie_path
        jar = MozillaCookieJar(str(cookie_path))
        jar.load(ignore_discard=True)
        assert 'PRIVATE=FAKE' in prepared_cookie(jar, 'https://origin.invalid/private/a')
        assert not prepared_cookie(jar, 'https://else.invalid/private/a')
        assert '--proto-redir' in command
        part.write_bytes(b'out')
        return SimpleNamespace(poll=lambda: 0, returncode=0)
    monkeypatch.setattr('core.fetcher.subprocess.Popen', launch)
    ok = Fetcher()._download_via_curl('https://origin.invalid/private/a', part, dest, {}, cookie_jar=scoped_test_jar())
    assert ok and dest.read_bytes() == b'out'
    assert not observed['cookie_path'].exists()


def test_doctor_covers_all_declared_core_dependencies():
    import ast
    import re
    from core.doctor import DEPENDENCY_SPEC
    project = (Path(__file__).parents[1] / 'pyproject.toml').read_text()
    declared = ast.literal_eval('[' + re.search(r'^dependencies = \[(.*?)\]', project, re.M | re.S)[1] + ']')
    checked = {spec for spec, _, required in DEPENDENCY_SPEC.values() if required}
    assert set(declared) == checked


def test_local_audio_full_pipeline_keeps_explicit_local_access(tmp_path, media_samples):
    from drivers.audio.local_audio import LocalAudioDriver
    source = tmp_path / 'source.flac'
    source.write_bytes(media_samples['.flac'])
    with patch('cli.get_default_drivers', return_value=[LocalAudioDriver()]):
        result = process_download(str(source), output_dir=str(tmp_path / 'output'), agent_mode=True)
    assert result['status'] == 'success'
    assert Verifier.verify(Path(result['primary_asset'])).valid


def test_audio_conversion_does_not_overwrite_existing_audio(tmp_path):
    from cli import _extract_audio_from_video
    video = tmp_path / 'same.mp4'
    existing = tmp_path / 'same.m4a'
    video.write_bytes(b'fake video')
    existing.write_bytes(b'ORIGINAL AUDIO')
    def produce(command, **kwargs):
        Path(command[-1]).write_bytes(b'NEW AUDIO' * 200)
        return SimpleNamespace(returncode=0)
    with patch('cli.shutil.which', return_value='/fake/ffmpeg'), patch('cli.subprocess.run', produce):
        result = _extract_audio_from_video(video)
    assert existing.read_bytes() == b'ORIGINAL AUDIO'
    assert result != existing and result.read_bytes() == b'NEW AUDIO' * 200
    assert not video.exists()


def test_mp3_container_correction_does_not_replace_companion(tmp_path, media_samples):
    original = media_samples['.m4a']
    companion = media_samples['.m4a'] + b'companion'
    package = AssetPackage('Track', 'test', assets=[
        data_asset('content.mp3', original), data_asset('Track.m4a', companion, 'companion'),
    ])
    with patch('cli.MusicUnlocker.transcode_to_mp3', return_value=False):
        result = run_package(package, tmp_path)
    assert result['status'] == 'success'
    assert Path(result['primary_asset']).read_bytes() == original
    assert Path(result['companion_files'][0]).read_bytes() == companion
    assert result['primary_asset'] != result['companion_files'][0]


def test_epub_svg_spine_is_accepted(tmp_path, epub_members):
    epub_members['OEBPS/book.opf'] = epub_members['OEBPS/book.opf'].replace(b'application/xhtml+xml', b'image/svg+xml')
    epub_members['OEBPS/text/chapter.xhtml'] = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
    path = tmp_path / 'svg.epub'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, payload in epub_members.items(): archive.writestr(name, payload)
    assert Verifier.verify(path).valid
