"""
Unit Tests for the Universal yt-dlp Fallback Driver
"""
import pytest

from core.exceptions import DownloadError, ExtractionError, FileTooLargeError
from core.router import Router
from drivers import get_default_drivers
from drivers.base import TargetAsset
from drivers.social.ytdlp_fallback import YtDlpFallbackDriver


def _fake_ydl(monkeypatch, info=None, error=None):
    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            if error:
                raise error
            return info

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)


def _video_info():
    return {
        "title": "Fallback demo",
        "description": "A description",
        "uploader": "Demo Creator",
        "extractor_key": "Generic",
        "webpage_url": "https://video.example.com/watch/1",
        "duration": 12,
        "view_count": 100,
        "tags": ["demo", "video"],
        "formats": [
            {
                "url": "https://cdn.example.com/hls.m3u8",
                "ext": "mp4",
                "protocol": "m3u8_native",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 1080,
            },
            {
                "url": "https://cdn.example.com/1080.mp4",
                "ext": "mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 1080,
                "filesize": 900 * 1024 * 1024,
            },
            {
                "url": "https://cdn.example.com/720.mp4",
                "ext": "mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 720,
                "filesize": 20 * 1024 * 1024,
            },
            {
                "url": "https://cdn.example.com/audio.m4a",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a",
                "abr": 128,
                "filesize": 2 * 1024 * 1024,
            },
        ],
    }


def test_can_handle_http_urls_only():
    driver = YtDlpFallbackDriver()
    assert driver.can_handle("https://www.kuaishou.com/short-video/abc")
    assert driver.can_handle("http://vimeo.com/123456")
    assert not driver.can_handle("三体")
    assert not driver.can_handle("70dbedfb04537d377cb093cdae645f37")
    assert not driver.can_handle("https://")
    assert not driver.can_handle("/tmp/local-video.mp4")
    assert not driver.can_handle("file:///tmp/local-video.mp4")


def test_prefers_progressive_http_stream_and_skips_oversized(monkeypatch):
    _fake_ydl(monkeypatch, info=_video_info())

    package = YtDlpFallbackDriver().extract("https://video.example.com/watch/1")

    assert package.platform == "ytdlp"
    assert package.primary_asset.url == "https://cdn.example.com/720.mp4"
    assert package.primary_asset.filename == "content.mp4"
    assert package.metadata["extractor"] == "Generic"
    assert package.metadata["tags"] == ["demo", "video"]
    assert package.metadata["sidecar_text"] == "A description"
    assert package.metadata["author"]["name"] == "Demo Creator"


def test_audio_only_selects_audio_track(monkeypatch):
    _fake_ydl(monkeypatch, info=_video_info())

    package = YtDlpFallbackDriver().extract(
        "https://video.example.com/watch/1", audio_only=True
    )

    assert package.primary_asset.url == "https://cdn.example.com/audio.m4a"
    assert package.primary_asset.filename == "content.m4a"


def test_hls_only_uses_ytdlp_native_download(monkeypatch):
    _fake_ydl(monkeypatch, info={
        "title": "HLS only",
        "formats": [{
            "url": "https://cdn.example.com/master.m3u8",
            "ext": "mp4",
            "protocol": "m3u8_native",
            "vcodec": "avc1",
            "acodec": "mp4a",
            "height": 720,
        }],
    })

    package = YtDlpFallbackDriver().extract("https://video.example.com/hls")

    asset = package.primary_asset
    assert asset.download_strategy == "ytdlp"
    assert asset.filename == "content.mp4"
    assert asset.download_options["format"] == "bv*+ba/b"
    assert asset.download_options["source_url"] == "https://video.example.com/hls"
    assert package.metadata["download_strategy"] == "ytdlp"


def test_hls_audio_only_uses_native_audio_selector(monkeypatch):
    _fake_ydl(monkeypatch, info={
        "title": "HLS audio",
        "formats": [
            {
                "url": "https://cdn.example.com/video.m3u8",
                "ext": "mp4",
                "protocol": "m3u8_native",
                "vcodec": "avc1",
                "acodec": "none",
                "height": 720,
            },
            {
                "url": "https://cdn.example.com/audio.m3u8",
                "ext": "m4a",
                "protocol": "m3u8_native",
                "vcodec": "none",
                "acodec": "mp4a",
                "abr": 128,
            },
        ],
    })

    package = YtDlpFallbackDriver().extract(
        "https://video.example.com/hls", audio_only=True
    )

    asset = package.primary_asset
    assert asset.download_strategy == "ytdlp"
    assert asset.filename == "content.m4a"
    assert asset.download_options["format"] == "ba/b"


def test_native_download_writes_destination(monkeypatch, tmp_path):
    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            output = self.opts["outtmpl"].replace("%(ext)s", "mp4")
            with open(output, "wb") as f:
                f.write(b"video-bytes")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    asset = TargetAsset(
        filename="content.mp4",
        url="https://video.example.com/hls",
        download_strategy="ytdlp",
        download_options={"source_url": "https://video.example.com/hls"},
    )
    dest = tmp_path / "out.mp4"

    size, final_path = YtDlpFallbackDriver().download_primary(
        asset, dest, max_bytes=1024 * 1024
    )

    assert size == len(b"video-bytes")
    assert final_path == dest
    assert dest.read_bytes() == b"video-bytes"
    assert not list(tmp_path.glob(".da-ytdlp-*"))


def test_native_download_enforces_size_limit(monkeypatch, tmp_path):
    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            output = self.opts["outtmpl"].replace("%(ext)s", "mp4")
            with open(output, "wb") as f:
                f.write(b"x" * 4096)

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    asset = TargetAsset(
        filename="content.mp4",
        url="https://video.example.com/hls",
        download_strategy="ytdlp",
        download_options={"source_url": "https://video.example.com/hls"},
    )

    with pytest.raises(FileTooLargeError):
        YtDlpFallbackDriver().download_primary(asset, tmp_path / "out.mp4", max_bytes=1024)
    assert not (tmp_path / "out.mp4").exists()


def test_native_download_failure_is_wrapped(monkeypatch, tmp_path):
    class FakeYoutubeDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            raise RuntimeError("network down")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    asset = TargetAsset(
        filename="content.mp4",
        url="https://video.example.com/hls",
        download_strategy="ytdlp",
    )

    with pytest.raises(DownloadError, match="yt-dlp fallback download failed"):
        YtDlpFallbackDriver().download_primary(asset, tmp_path / "out.mp4", max_bytes=1024)


def test_playlist_is_rejected_instead_of_selecting_entry(monkeypatch):
    _fake_ydl(monkeypatch, info={
        "_type": "playlist",
        "entries": [
            {
                "title": "First",
                "formats": [{
                    "url": "https://cdn.example.com/first.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                }],
            }
        ],
    })

    with pytest.raises(ExtractionError, match="single video/audio"):
        YtDlpFallbackDriver().extract("https://video.example.com/list")


def test_live_stream_is_rejected(monkeypatch):
    _fake_ydl(monkeypatch, info={"is_live": True, "formats": []})

    with pytest.raises(ExtractionError, match="Live streams are not supported"):
        YtDlpFallbackDriver().extract("https://live.example.com/room/1")


def test_extraction_failure_mentions_drm_and_login(monkeypatch):
    _fake_ydl(monkeypatch, error=RuntimeError("Unsupported URL: https://example.com"))

    with pytest.raises(ExtractionError, match="region-locked, DRM-protected, or require login"):
        YtDlpFallbackDriver().extract("https://example.com/watch")


def test_direct_file_info_without_formats(monkeypatch):
    _fake_ydl(monkeypatch, info={
        "title": "Direct clip",
        "url": "https://cdn.example.com/direct.mp4",
        "ext": "mp4",
        "protocol": "https",
    })

    package = YtDlpFallbackDriver().extract("https://example.com/direct")

    assert package.primary_asset.url == "https://cdn.example.com/direct.mp4"
    assert package.primary_asset.filename == "content.mp4"


def test_approx_filesize_is_not_used_as_exact_size(monkeypatch):
    _fake_ydl(monkeypatch, info={
        "title": "Approximate",
        "formats": [{
            "url": "https://cdn.example.com/approx.mp4",
            "ext": "mp4",
            "vcodec": "avc1",
            "acodec": "mp4a",
            "filesize_approx": 20 * 1024 * 1024,
        }],
    })

    package = YtDlpFallbackDriver().extract("https://video.example.com/approx")

    # Exact-size verification would reject a complete download a few bytes off.
    assert package.primary_asset.expected_size is None


def test_extract_honors_custom_max_bytes(monkeypatch):
    info = {
        "title": "Sizes",
        "formats": [
            {
                "url": "https://cdn.example.com/1080.mp4",
                "ext": "mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 1080,
                "filesize": 700 * 1024 * 1024,
            },
            {
                "url": "https://cdn.example.com/720.mp4",
                "ext": "mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 720,
                "filesize": 20 * 1024 * 1024,
            },
        ],
    }
    driver = YtDlpFallbackDriver()

    _fake_ydl(monkeypatch, info=info)
    default_package = driver.extract("https://video.example.com/sizes")
    assert default_package.primary_asset.url == "https://cdn.example.com/720.mp4"

    _fake_ydl(monkeypatch, info=info)
    raised_package = driver.extract(
        "https://video.example.com/sizes", max_bytes=800 * 1024 * 1024
    )
    assert raised_package.primary_asset.url == "https://cdn.example.com/1080.mp4"


def test_native_download_keeps_actual_container(monkeypatch, tmp_path):
    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            output = self.opts["outtmpl"].replace("%(ext)s", "mkv")
            with open(output, "wb") as f:
                f.write(b"merged-mkv")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    asset = TargetAsset(
        filename="content.mp4",
        url="https://video.example.com/hls",
        download_strategy="ytdlp",
    )
    dest = tmp_path / "out.mp4"

    size, final_path = YtDlpFallbackDriver().download_primary(
        asset, dest, max_bytes=1024 * 1024
    )

    assert size == len(b"merged-mkv")
    assert final_path == tmp_path / "out.mkv"
    assert final_path.read_bytes() == b"merged-mkv"
    assert not dest.exists()


def test_native_download_drops_unscoped_credential_headers(monkeypatch, tmp_path):
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            output = self.opts["outtmpl"].replace("%(ext)s", "mp4")
            with open(output, "wb") as f:
                f.write(b"ok")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    asset = TargetAsset(
        filename="content.mp4",
        url="https://video.example.com/hls",
        download_strategy="ytdlp",
        headers={"Cookie": "sid=abc", "User-Agent": "UA", "Authorization": "Bearer t"},
    )

    YtDlpFallbackDriver().download_primary(
        asset, tmp_path / "out.mp4", max_bytes=1024 * 1024
    )

    assert captured["http_headers"] == {"User-Agent": "UA"}


def test_default_router_falls_back_for_unclaimed_video_sites():
    router = Router(get_default_drivers())

    for url in (
        "https://www.kuaishou.com/short-video/abc",
        "https://www.ixigua.com/1234567890",
        "https://vimeo.com/123456789",
        "https://www.tiktok.com/@creator/video/1234567890",
    ):
        driver, _ = router.route(url)
        assert driver.name == "ytdlp", url


def test_default_router_keeps_specialized_drivers_first():
    router = Router(get_default_drivers())

    cases = {
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "YouTubeDriver",
        "https://www.bilibili.com/video/BV1xx411c7mD": "BilibiliDriver",
        "https://v.douyin.com/abcde/": "DouyinDriver",
        "https://pan.quark.cn/s/a9f0e1b2c3d4": "QuarkDriver",
        "https://zhuanlan.zhihu.com/p/123456": "WebArticleDriver",
    }
    for url, expected in cases.items():
        driver, _ = router.route(url)
        assert type(driver).__name__ == expected, url

    # Non-URL inputs must still reach their own drivers.
    driver, _ = router.route("三体")
    assert driver.name == "shadow_library"
