"""
Unit Tests for Phase 4 Drivers:
YouTube, Twitter/X, Instagram, Weibo, Apple Podcasts, Novel, DOI
"""
import pytest
from unittest.mock import MagicMock

from core.exceptions import ExtractionError
from drivers.social.youtube import YouTubeDriver
from drivers.social.twitter import TwitterDriver
from drivers.social.instagram import InstagramDriver
from drivers.social.weibo import WeiboDriver
from drivers.audio.apple_podcasts import ApplePodcastsDriver
from drivers.books.novel import NovelDriver
from drivers.books.doi import DOIDriver
from drivers.software.ms_store import MicrosoftStoreDriver

def test_youtube_driver_can_handle():
    driver = YouTubeDriver()
    assert driver.can_handle("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert driver.can_handle("https://youtu.be/dQw4w9WgXcQ")
    assert driver.can_handle("https://www.youtube.com/shorts/abcdef12345")
    assert not driver.can_handle("https://v.douyin.com/abcde/")

def test_youtube_audio_only_uses_independent_audio_track(monkeypatch):
    class FakeYoutubeDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download=False):
            return {
                "title": "Audio test",
                "formats": [
                    {
                        "url": "https://example.com/audio.m4a",
                        "ext": "m4a",
                        "acodec": "mp4a",
                        "vcodec": "none",
                        "abr": 128,
                        "filesize": 1024,
                    },
                    {
                        "url": "https://example.com/video.mp4",
                        "ext": "mp4",
                        "acodec": "mp4a",
                        "vcodec": "avc1",
                        "filesize": 2048,
                    },
                ],
            }

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    package = YouTubeDriver().extract(
        "https://www.youtube.com/watch?v=12345678901",
        audio_only=True,
    )
    assert package.primary_asset.url == "https://example.com/audio.m4a"
    assert package.primary_asset.filename == "content.m4a"


def test_twitter_driver_can_handle():
    driver = TwitterDriver()
    assert driver.can_handle("https://twitter.com/OpenAI/status/1234567890123456789")
    assert driver.can_handle("https://x.com/elonmusk/status/9876543210987654321")
    assert not driver.can_handle("https://instagram.com/p/abcde/")

def test_instagram_driver_can_handle():
    driver = InstagramDriver()
    assert driver.can_handle("https://www.instagram.com/p/CzX9yZ-r123/")
    assert driver.can_handle("https://www.instagram.com/reel/C8xyzAbCdEf/")
    assert not driver.can_handle("https://x.com/user/status/123")

def test_weibo_driver_can_handle():
    driver = WeiboDriver()
    assert driver.can_handle("https://weibo.com/1234567890/O5xxxxxxx")
    assert driver.can_handle("https://m.weibo.cn/detail/4999999999999999")
    assert driver.can_handle("https://weibo.cn/status/4999999999999999")
    assert not driver.can_handle("https://pan.baidu.com/s/1xxxx")

def test_apple_podcasts_driver_can_handle():
    driver = ApplePodcastsDriver()
    assert driver.can_handle("https://podcasts.apple.com/us/podcast/huberman-lab/id1545953110?i=1000799372105")
    assert driver.can_handle("https://podcasts.apple.com/cn/podcast/id1234567890")
    assert not driver.can_handle("https://www.xiaoyuzhoufm.com/episode/12345")

def test_novel_driver_can_handle():
    driver = NovelDriver()
    assert driver.can_handle("https://www.biquge.com/book/12345/")
    assert driver.can_handle("https://www.69shuba.com/txt/12345/")
    assert not driver.can_handle("https://arxiv.org/abs/2310.06825")


def _novel_response(text):
    response = MagicMock()
    response.encoding = "utf-8"
    response.text = text
    return response


def test_novel_extract_fetches_beyond_thirty_chapters(monkeypatch):
    links = "".join(f'<a href="/chapter/{idx}/">第{idx}章</a>' for idx in range(1, 32))
    index_html = f'<html><body><h1>Demo</h1><div id="list">{links}</div></body></html>'

    def fake_get(url, **kwargs):
        if "/chapter/" in url:
            idx = url.rstrip("/").rsplit("/", 1)[-1]
            return _novel_response(f'<html><body><div id="content">正文 {idx}</div></body></html>')
        return _novel_response(index_html)

    monkeypatch.setattr("drivers.books.novel.requests.get", fake_get)
    package = NovelDriver().extract("https://www.biquge.com/book/12345/")
    assert package.metadata["metrics"]["fetched_chapters"] == 31
    assert "第31章" in package.metadata["sidecar_text"]
    assert "正文 31" in package.metadata["sidecar_text"]


def test_novel_extract_rejects_missing_chapter_body(monkeypatch):
    index_html = (
        '<html><body><h1>Demo</h1><div id="list">'
        '<a href="/chapter/1/">第一章</a><a href="/chapter/2/">第二章</a>'
        '</div></body></html>'
    )

    def fake_get(url, **kwargs):
        if url.endswith("/chapter/2/"):
            raise Timeout("chapter timeout")
        if url.endswith("/chapter/1/"):
            return _novel_response('<html><body><div id="content">正文</div></body></html>')
        return _novel_response(index_html)

    monkeypatch.setattr("drivers.books.novel.requests.get", fake_get)
    with pytest.raises(ExtractionError, match="Novel extraction incomplete: 1/2"):
        NovelDriver().extract("https://www.biquge.com/book/12345/")


def test_doi_driver_can_handle():
    driver = DOIDriver()
    assert driver.can_handle("https://doi.org/10.1038/nature12373")
    assert driver.can_handle("doi:10.1360/SSV-2023-0180")
    assert driver.can_handle("10.1145/3372278.3390678")
    assert not driver.can_handle("https://youtube.com/watch?v=123")

def test_ms_store_driver_can_handle():
    driver = MicrosoftStoreDriver()
    assert driver.can_handle("https://apps.microsoft.com/detail/9nt1r1c2hh7j")
    assert driver.can_handle("https://www.microsoft.com/store/productId/9N0DX20HK701")
    assert driver.can_handle("9nt1r1c2hh7j")
    assert not driver.can_handle("https://github.com/torvalds/linux")
