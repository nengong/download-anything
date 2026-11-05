"""
Unit Tests for Phase 4 Drivers:
YouTube, Twitter/X, Instagram, Weibo, Apple Podcasts, Novel, DOI
"""
import json
import subprocess
import sys

import pytest
from unittest.mock import MagicMock

from core.exceptions import ExtractionError
from core.router import Router
from drivers import get_default_drivers
from drivers.social.ytdlp_fallback import YtDlpFallbackDriver
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
    assert package.primary_asset.url == "https://www.youtube.com/watch?v=12345678901"
    assert package.primary_asset.filename == "content.m4a"
    assert package.primary_asset.download_strategy == "ytdlp"
    assert package.primary_asset.download_options == {
        "source_url": "https://www.youtube.com/watch?v=12345678901",
        "format": "ba/b",
    }
    assert package.primary_asset.expected_size is None


def _mock_youtube_info(monkeypatch, info):
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.extract_info.return_value = info
    factory = MagicMock(return_value=ydl)
    monkeypatch.setattr("yt_dlp.YoutubeDL", factory)
    return factory, ydl


@pytest.mark.parametrize("source_url", [
    "https://www.youtube.com/watch?v=12345678901",
    "https://www.youtube.com/shorts/12345678901",
    "https://youtu.be/12345678901?t=12",
    "https://m.youtube.com/watch?v=12345678901",
])
def test_youtube_split_tracks_use_native_download_and_canonical_url(monkeypatch, source_url):
    factory, ydl = _mock_youtube_info(monkeypatch, {
        "title": "Split tracks",
        "formats": [
            {"url": "https://example.com/video.mp4", "ext": "mp4",
             "vcodec": "avc1", "acodec": "none", "height": 2160,
             "filesize_approx": 900 * 1024 * 1024},
            {"url": "https://example.com/audio.m4a", "ext": "m4a",
             "vcodec": "none", "acodec": "mp4a", "filesize": 1024},
        ],
    })
    router = Router(get_default_drivers())
    driver = router.find_driver(router.clean_input(source_url))
    assert type(driver) is YouTubeDriver
    assert YouTubeDriver.download_primary is YtDlpFallbackDriver.download_primary
    package = driver.extract(source_url)
    canonical_url = "https://www.youtube.com/watch?v=12345678901"
    assert package.platform == "youtube"
    assert package.original_url == canonical_url
    assert package.primary_asset.url == canonical_url
    assert package.primary_asset.filename == "content.mp4"
    assert package.primary_asset.download_strategy == "ytdlp"
    assert package.primary_asset.download_options == {
        "source_url": canonical_url,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
    }
    assert package.primary_asset.expected_size is None
    ydl.extract_info.assert_called_once_with(canonical_url, download=False)
    assert factory.call_args.args[0] == {
        "quiet": True, "no_warnings": True, "extract_flat": False,
        "skip_download": True, "noplaylist": True, "socket_timeout": 15,
    }


@pytest.mark.parametrize("size_field", ["filesize", "filesize_approx"])
def test_youtube_progressive_size_is_not_final_size(monkeypatch, size_field):
    _mock_youtube_info(monkeypatch, {
        "formats": [{"url": "https://example.com/video.mp4", "ext": "mp4",
                     "vcodec": "avc1", "acodec": "mp4a", size_field: 2048}],
    })
    asset = YouTubeDriver().extract("https://youtu.be/12345678901").primary_asset
    assert asset.expected_size is None
    assert asset.download_strategy == "ytdlp"
    assert asset.url == "https://www.youtube.com/watch?v=12345678901"


@pytest.mark.parametrize("info", [
    {"title": "No formats"},
    {"formats": []},
    {"formats": None},
    {"formats": [{"ext": "mp4", "vcodec": "avc1"}]},
])
def test_youtube_rejects_missing_downloadable_media(monkeypatch, info):
    _mock_youtube_info(monkeypatch, info)
    with pytest.raises(ExtractionError, match="Could not resolve downloadable stream"):
        YouTubeDriver().extract("https://youtu.be/12345678901")


def test_youtube_top_level_media_url_uses_native_download(monkeypatch):
    _mock_youtube_info(monkeypatch, {
        "url": "https://example.com/manifest.m3u8", "formats": [],
    })
    asset = YouTubeDriver().extract("https://youtu.be/12345678901").primary_asset
    assert asset.download_strategy == "ytdlp"
    assert asset.download_options["format"] == "bv*+ba/b"


@pytest.mark.parametrize("ext", ["opus", "ogg", "m4a"])
def test_youtube_audio_extension_uses_native_audio_estimate(monkeypatch, ext):
    info = {"formats": [{"url": f"https://example.com/audio.{ext}",
                         "ext": ext, "vcodec": "none", "acodec": "opus"}]}
    _mock_youtube_info(monkeypatch, info)
    asset = YouTubeDriver().extract("https://youtu.be/12345678901", audio_only=True).primary_asset
    assert asset.filename == f"content.{YtDlpFallbackDriver._native_audio_ext(info)}"
    assert asset.filename == f"content.{ext}"
    assert asset.download_options["format"] == "ba/b"
    assert "merge_output_format" not in asset.download_options
    assert asset.expected_size is None


def test_youtube_preserves_metadata_cover_and_subtitles(monkeypatch):
    _mock_youtube_info(monkeypatch, {
        "title": "Original title", "description": "Original description",
        "uploader": "Creator", "channel_id": "channel-id", "upload_date": "20260101",
        "view_count": 123, "like_count": 45, "duration": 67,
        "thumbnail": "https://example.com/cover.jpg",
        "subtitles": {
            "en": [{"ext": "vtt", "url": "https://example.com/en.vtt"}],
            "zh-Hans": [{"ext": "vtt", "url": "https://example.com/zh.vtt"}],
        },
        "formats": [{"url": "https://example.com/video.mp4"}],
    })
    package = YouTubeDriver().extract("https://youtu.be/12345678901")
    assert package.title == "Original title"
    assert package.metadata == {
        "title": "Original title",
        "original_url": "https://www.youtube.com/watch?v=12345678901",
        "author": {"id": "channel-id", "name": "Creator"},
        "created_at": "20260101",
        "metrics": {"views": 123, "likes": 45, "duration_seconds": 67},
        "sidecar_text": "Original description",
    }
    assert [(a.filename, a.url) for a in package.assets[1:]] == [
        ("cover.jpg", "https://example.com/cover.jpg"),
        ("subtitle.vtt", "https://example.com/zh.vtt"),
    ]
    assert all(a.download_strategy == "http" for a in package.assets[1:])


def test_twitter_driver_can_handle():
    driver = TwitterDriver()
    assert driver.can_handle("https://twitter.com/OpenAI/status/1234567890123456789")
    assert driver.can_handle("https://x.com/elonmusk/status/9876543210987654321")
    assert not driver.can_handle("https://instagram.com/p/abcde/")

@pytest.mark.parametrize("source_url", [
    "https://x.com/OpenAI/status/123",
    "https://twitter.com/OpenAI/status/123?ref_src=test",
    "https://mobile.twitter.com/OpenAI/status/123/video/1",
    "https://m.x.com/OpenAI/status/123",
    "https://www.twitter.com/#!/OpenAI/status/123",
])
def test_twitter_split_tracks_use_canonical_native_download(monkeypatch, source_url):
    factory, ydl = _mock_youtube_info(monkeypatch, {
        "formats": [
            {"url": "https://example.com/video.mp4", "ext": "mp4",
             "vcodec": "avc1", "acodec": "none", "height": 2160,
             "filesize_approx": 900 * 1024 * 1024},
            {"url": "https://example.com/audio.m4a", "ext": "m4a",
             "vcodec": "none", "acodec": "mp4a", "filesize": 1024},
        ],
    })
    router = Router(get_default_drivers())
    driver = router.find_driver(router.clean_input(source_url))
    assert type(driver) is TwitterDriver
    assert TwitterDriver.download_primary is YtDlpFallbackDriver.download_primary
    package = driver.extract(source_url)
    canonical = "https://x.com/OpenAI/status/123"
    assert package.platform == "twitter"
    assert package.original_url == canonical
    asset = package.primary_asset
    assert asset.url == canonical
    assert asset.filename == "content.mp4"
    assert asset.expected_size is None
    assert asset.download_strategy == "ytdlp"
    assert asset.download_options == {
        "source_url": canonical, "format": "bv*+ba/b", "merge_output_format": "mp4",
    }
    ydl.extract_info.assert_called_once_with(canonical, download=False)
    assert factory.call_args.args[0] == {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": True, "socket_timeout": 15,
    }


@pytest.mark.parametrize("size_field", ["filesize", "filesize_approx"])
def test_twitter_progressive_size_is_not_final_size(monkeypatch, size_field):
    _mock_youtube_info(monkeypatch, {
        "formats": [{"url": "https://example.com/video.mp4", size_field: 2048}],
    })
    asset = TwitterDriver().extract("https://x.com/user/status/123").primary_asset
    assert asset.expected_size is None
    assert asset.download_strategy == "ytdlp"


@pytest.mark.parametrize("ext", ["opus", "ogg", "m4a", None])
def test_twitter_audio_only_uses_native_audio_extension(monkeypatch, ext):
    info = {"formats": [
        {"url": "https://example.com/video.mp4", "ext": "mp4",
         "vcodec": "avc1", "acodec": "none", "tbr": 9000},
        {"url": "https://example.com/audio", "ext": ext,
         "vcodec": "none", "acodec": "opus", "abr": 128},
    ]}
    _mock_youtube_info(monkeypatch, info)
    asset = TwitterDriver().extract("https://twitter.com/user/status/123", audio_only=True).primary_asset
    assert asset.filename == f"content.{YtDlpFallbackDriver._native_audio_ext(info)}"
    assert asset.filename == f"content.{ext or 'm4a'}"
    assert asset.download_strategy == "ytdlp"
    assert asset.expected_size is None
    assert asset.download_options == {
        "source_url": "https://x.com/user/status/123", "format": "ba/b",
    }


@pytest.mark.parametrize("formats", [[], None, [{"ext": "mp4"}]])
def test_twitter_top_level_url_is_downloadable_media(monkeypatch, formats):
    _mock_youtube_info(monkeypatch, {
        "formats": formats, "url": "https://example.com/media.m3u8",
    })
    asset = TwitterDriver().extract("https://x.com/user/status/123").primary_asset
    assert asset.download_strategy == "ytdlp"
    assert asset.download_options["format"] == "bv*+ba/b"


@pytest.mark.parametrize("info", [
    {"title": "No media"}, {"formats": []}, {"formats": None},
    {"formats": [{"ext": "mp4"}, {"url": ""}]},
])
def test_twitter_rejects_missing_media(monkeypatch, info):
    _mock_youtube_info(monkeypatch, info)
    with pytest.raises(ExtractionError, match="No downloadable media"):
        TwitterDriver().extract("https://x.com/user/status/123")


@pytest.mark.parametrize("info", [
    {"_type": "playlist"}, {"_type": "multi_video"},
    {"entries": []},
    {"entries": [{"url": "https://example.com/one.mp4"}]},
    {"entries": [{"url": "https://example.com/one.mp4"},
                 {"url": "https://example.com/two.mp4"}]},
])
def test_twitter_rejects_playlist_without_selecting_entry(monkeypatch, info):
    _mock_youtube_info(monkeypatch, {
        **info, "thumbnail": "https://example.com/cover.jpg",
    })
    with pytest.raises(ExtractionError, match="single video"):
        TwitterDriver().extract("https://x.com/user/status/123")


def test_twitter_preserves_metadata_cover_and_media_headers(monkeypatch, tmp_path):
    description = "Original tweet description " * 4
    _mock_youtube_info(monkeypatch, {
        "title": "Ignored title", "description": description,
        "uploader": "Creator", "uploader_id": "creator-id", "upload_date": "20260101",
        "like_count": 12, "repost_count": 34, "comment_count": 56,
        "thumbnail": "https://example.com/cover.jpg",
        "http_headers": {"Referer": "https://x.com/", "User-Agent": "Test agent"},
        "formats": [
            {"url": "https://example.com/video.mp4",
             "http_headers": {"Origin": "https://x.com"}},
            {"url": "https://example.com/audio.m4a",
             "http_headers": {"Accept": "*/*"}},
        ],
    })
    driver = TwitterDriver()
    package = driver.extract("https://twitter.com/user/status/123")
    assert package.title == description[:60].strip()
    assert package.metadata == {
        "title": description[:60].strip(),
        "original_url": "https://x.com/user/status/123",
        "author": {"id": "creator-id", "name": "Creator"},
        "created_at": "20260101",
        "metrics": {"likes": 12, "reposts": 34, "comments": 56},
        "sidecar_text": description,
    }
    assert [(a.filename, a.url, a.download_strategy) for a in package.assets[1:]] == [
        ("cover.jpg", "https://example.com/cover.jpg", "http"),
    ]
    assert package.assets[1].headers == {"User-Agent": "Mozilla/5.0"}
    assert package.primary_asset.headers == {
        "User-Agent": "Test agent", "Referer": "https://x.com/",
        "Origin": "https://x.com", "Accept": "*/*",
    }
    # Exercise the inherited downloader with synthetic headers and local output only.
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    factory = MagicMock(return_value=ydl)
    monkeypatch.setattr("yt_dlp.YoutubeDL", factory)

    def download(urls):
        from pathlib import Path
        assert urls == ["https://x.com/user/status/123"]
        output = factory.call_args.args[0]["outtmpl"].replace("%(ext)s", "mp4")
        Path(output).write_bytes(b"mock merged media")

    ydl.download.side_effect = download
    size, path = driver.download_primary(package.primary_asset, tmp_path / "content.mp4", 1024)
    assert path.read_bytes() == b"mock merged media"
    assert size == len(b"mock merged media")
    assert factory.call_args.args[0]["http_headers"] == package.primary_asset.headers
    assert factory.call_args.args[0]["format"] == "bv*+ba/b"
    assert factory.call_args.args[0]["merge_output_format"] == "mp4"


@pytest.mark.parametrize("audio_only", [False, True])
@pytest.mark.parametrize("formats", [[], None, [{"ext": "mp4"}]])
def test_twitter_image_fallback_is_unchanged(monkeypatch, audio_only, formats):
    _mock_youtube_info(monkeypatch, {
        "title": "Image tweet", "thumbnail": "https://example.com/image.jpg",
        "formats": formats,
    })
    package = TwitterDriver().extract("https://x.com/user/status/123", audio_only=audio_only)
    assert len(package.assets) == 1
    asset = package.primary_asset
    assert asset.filename == "content.jpg"
    assert asset.url == "https://example.com/image.jpg"
    assert asset.download_strategy == "http"
    assert asset.download_options == {}
    assert asset.expected_size is None
    assert asset.headers == {"User-Agent": "Mozilla/5.0"}
    assert package.metadata["author"] == {"id": "user", "name": "user"}


def test_twitter_gallery_fallback_extracts_ordered_photo_collection(monkeypatch):
    messages = [[2, {
        "tweet_id": 123, "count": 2, "content": "A photo post", "date": "2026-01-02",
        "author": {"id": 9, "name": "user", "nick": "User Nick"},
    }]]
    for num, suffix in [(2, "second"), (1, "first"), (2, "second")]:
        messages.append([3, f"https://pbs.twimg.com/media/{suffix}?format=jpg&name=orig", {
            "tweet_id": 123, "count": 2, "type": "photo", "num": num, "extension": "jpg",
            "content": "A photo post", "date": "2026-01-02",
            "author": {"id": 9, "name": "user", "nick": "User Nick"},
        }])
    run = MagicMock(return_value=MagicMock(returncode=0, stdout=__import__("json").dumps(messages), stderr=""))
    monkeypatch.setattr("drivers.social.twitter.subprocess.run", run)
    package = TwitterDriver()._extract_photos("https://x.com/user/status/123", "user", "123")
    assert [asset.filename for asset in package.assets] == ["content.jpg", "image_02.jpg"]
    assert package.metadata["author"] == {"id": 9, "name": "user", "nick": "User Nick"}
    assert package.metadata["metrics"]["image_count"] == 2
    assert run.call_args.args[0] == [
        __import__("sys").executable, "-m", "gallery_dl", "--config-ignore", "--no-input",
        "--dump-json", "--retries", "0", "--http-timeout", "15",
        "-o", "extractor.twitter.quoted=false", "-o", "extractor.twitter.replies=false",
        "https://x.com/user/status/123",
    ]
    assert run.call_args.kwargs == {"capture_output": True, "text": True, "timeout": 60}


def test_twitter_gallery_fallback_rejects_mixed_media_and_incomplete_count(monkeypatch):
    base = {"tweet_id": 123, "count": 2, "type": "video", "num": 1, "extension": "mp4"}
    mixed = [[2, {"tweet_id": 123, "count": 2}], [3, "https://pbs.twimg.com/media/a?format=jpg&name=orig", base]]
    run = MagicMock(return_value=MagicMock(returncode=0, stdout=__import__("json").dumps(mixed), stderr=""))
    monkeypatch.setattr("drivers.social.twitter.subprocess.run", run)
    with pytest.raises(ExtractionError, match="mixed video/photo"):
        TwitterDriver()._extract_photos("https://x.com/user/status/123", "user", "123")


def test_twitter_yt_dlp_no_video_uses_gallery_fallback(monkeypatch):
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.extract_info.side_effect = Exception("No video formats found")
    monkeypatch.setattr("yt_dlp.YoutubeDL", MagicMock(return_value=ydl))
    fallback = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(TwitterDriver, "_extract_photos", fallback)
    TwitterDriver().extract("https://x.com/user/status/123")
    fallback.assert_called_once_with("https://x.com/user/status/123", "user", "123")


    driver = InstagramDriver()
    assert driver.can_handle("https://www.instagram.com/p/CzX9yZ-r123/")
    assert driver.can_handle("https://www.instagram.com/reel/C8xyzAbCdEf/")
    assert not driver.can_handle("https://x.com/user/status/123")

@pytest.mark.parametrize("source_url", [
    "https://www.instagram.com/reel/C8xyzAbCdEf/",
    "https://instagram.com/p/C8xyzAbCdEf/?img_index=1",
    "https://www.instagram.com/tv/C8xyzAbCdEf/",
    "https://instagram.com/reels/C8xyzAbCdEf/",
])
def test_instagram_split_tracks_use_canonical_native_download(monkeypatch, source_url):
    factory, ydl = _mock_youtube_info(monkeypatch, {
        "formats": [
            {"url": "https://example.com/video.mp4", "ext": "mp4",
             "vcodec": "avc1", "acodec": "none", "height": 2160,
             "filesize_approx": 900 * 1024 * 1024},
            {"url": "https://example.com/audio.m4a", "ext": "m4a",
             "vcodec": "none", "acodec": "mp4a", "filesize": 1024},
        ],
    })
    router = Router(get_default_drivers())
    driver = router.find_driver(router.clean_input(source_url))
    assert type(driver) is InstagramDriver
    assert InstagramDriver.download_primary is YtDlpFallbackDriver.download_primary
    package = driver.extract(source_url)
    canonical = "https://www.instagram.com/p/C8xyzAbCdEf/"
    assert package.platform == "instagram"
    assert package.original_url == canonical
    asset = package.primary_asset
    assert asset.url == canonical
    assert asset.filename == "content.mp4"
    assert asset.expected_size is None
    assert asset.download_strategy == "ytdlp"
    assert asset.download_options == {
        "source_url": canonical, "format": "bv*+ba/b", "merge_output_format": "mp4",
    }
    ydl.extract_info.assert_called_once_with(canonical, download=False, process=False)
    assert factory.call_args.args[0] == {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": True, "socket_timeout": 15,
    }


@pytest.mark.parametrize("size_field", ["filesize", "filesize_approx"])
def test_instagram_progressive_size_is_not_final_size(monkeypatch, size_field):
    _mock_youtube_info(monkeypatch, {
        "formats": [{"url": "https://example.com/video.mp4", size_field: 2048}],
        size_field: 4096,
    })
    asset = InstagramDriver().extract("https://instagram.com/reel/abc/").primary_asset
    assert asset.expected_size is None
    assert asset.download_strategy == "ytdlp"
    assert asset.url == "https://www.instagram.com/p/abc/"


@pytest.mark.parametrize("ext", ["opus", "ogg", "m4a", None])
def test_instagram_audio_only_uses_native_audio_extension(monkeypatch, ext):
    info = {"formats": [
        {"url": "https://example.com/video.mp4", "ext": "mp4",
         "vcodec": "avc1", "acodec": "none", "tbr": 9000},
        {"url": "https://example.com/audio", "ext": ext,
         "vcodec": "none", "acodec": "opus", "abr": 128},
    ]}
    _mock_youtube_info(monkeypatch, info)
    asset = InstagramDriver().extract("https://instagram.com/reel/abc/", audio_only=True).primary_asset
    assert asset.filename == f"content.{YtDlpFallbackDriver._native_audio_ext(info)}"
    assert asset.filename == f"content.{ext or 'm4a'}"
    assert asset.download_strategy == "ytdlp"
    assert asset.expected_size is None
    assert asset.download_options == {
        "source_url": "https://www.instagram.com/p/abc/", "format": "ba/b",
    }


@pytest.mark.parametrize("formats", [[], None, [{"ext": "mp4"}]])
def test_instagram_top_level_url_is_downloadable_media(monkeypatch, formats):
    _mock_youtube_info(monkeypatch, {
        "formats": formats, "url": "https://example.com/media.m3u8",
    })
    asset = InstagramDriver().extract("https://instagram.com/reel/abc/").primary_asset
    assert asset.download_strategy == "ytdlp"
    assert asset.url == "https://www.instagram.com/p/abc/"
    assert asset.download_options["format"] == "bv*+ba/b"


@pytest.mark.parametrize("info", [
    {"title": "No media"}, {"formats": []}, {"formats": None},
    {"formats": [{"ext": "mp4"}, {"url": ""}]},
])
def test_instagram_rejects_missing_media(monkeypatch, info):
    _mock_youtube_info(monkeypatch, info)
    with pytest.raises(ExtractionError, match="No downloadable media"):
        InstagramDriver().extract("https://instagram.com/reel/abc/")


@pytest.mark.parametrize("info", [None, {}])
def test_instagram_rejects_empty_metadata(monkeypatch, info):
    _mock_youtube_info(monkeypatch, info)
    with pytest.raises(ExtractionError, match="Empty metadata"):
        InstagramDriver().extract("https://instagram.com/reel/abc/")


@pytest.mark.parametrize("info", [
    {"_type": "playlist"}, {"_type": "multi_video"},
    {"entries": []}, {"entries": None},
    {"entries": [{"url": "https://example.com/one.mp4"}]},
    {"entries": [{"url": "https://example.com/one.mp4"},
                 {"url": "https://example.com/two.mp4"}]},
])
def test_instagram_rejects_playlist_without_selecting_entry(monkeypatch, info):
    _mock_youtube_info(monkeypatch, {
        **info, "thumbnail": "https://example.com/cover.jpg",
        "url": "https://example.com/video.mp4",
    })
    with pytest.raises(ExtractionError, match="single video"):
        InstagramDriver().extract("https://instagram.com/reel/abc/")


def test_instagram_preserves_metadata_cover_and_media_headers(monkeypatch, tmp_path):
    description = "Original Instagram description " * 4
    _mock_youtube_info(monkeypatch, {
        "title": "Ignored title", "description": description,
        "uploader": "Creator", "uploader_id": "creator-id", "upload_date": "20260101",
        "like_count": 12, "comment_count": 56,
        "thumbnail": "https://example.com/cover.jpg",
        "http_headers": {"Referer": "https://www.instagram.com/", "User-Agent": "Test agent"},
        "formats": [
            {"url": "https://example.com/video.mp4",
             "http_headers": {"Origin": "https://www.instagram.com"}},
            {"url": "https://example.com/audio.m4a",
             "http_headers": {"Accept": "*/*", "Empty": "", "Invalid": None}},
        ],
    })
    driver = InstagramDriver()
    package = driver.extract("https://instagram.com/reel/abc/")
    assert package.title == description[:60].strip()
    assert package.metadata == {
        "title": description[:60].strip(),
        "original_url": "https://www.instagram.com/p/abc/",
        "author": {"id": "creator-id", "name": "Creator"},
        "created_at": "20260101",
        "metrics": {"likes": 12, "comments": 56},
        "sidecar_text": description,
    }
    assert [(a.filename, a.url, a.download_strategy) for a in package.assets[1:]] == [
        ("cover.jpg", "https://example.com/cover.jpg", "http"),
    ]
    assert package.assets[1].headers == {"User-Agent": "Mozilla/5.0"}
    assert package.primary_asset.headers == {
        "User-Agent": "Test agent", "Referer": "https://www.instagram.com/",
        "Origin": "https://www.instagram.com", "Accept": "*/*",
    }
    # Exercise the inherited downloader with synthetic headers and local output only.
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    factory = MagicMock(return_value=ydl)
    monkeypatch.setattr("yt_dlp.YoutubeDL", factory)

    def download(urls):
        from pathlib import Path
        assert urls == ["https://www.instagram.com/p/abc/"]
        output = factory.call_args.args[0]["outtmpl"].replace("%(ext)s", "mp4")
        Path(output).write_bytes(b"mock merged media")

    ydl.download.side_effect = download
    size, path = driver.download_primary(package.primary_asset, tmp_path / "content.mp4", 1024)
    assert path.read_bytes() == b"mock merged media"
    assert size == len(b"mock merged media")
    assert factory.call_args.args[0]["http_headers"] == package.primary_asset.headers
    assert factory.call_args.args[0]["format"] == "bv*+ba/b"
    assert factory.call_args.args[0]["merge_output_format"] == "mp4"


@pytest.mark.parametrize("audio_only", [False, True])
@pytest.mark.parametrize("formats", [[], None, [{"ext": "mp4"}]])
def test_instagram_image_fallback_is_unchanged(monkeypatch, audio_only, formats):
    _mock_youtube_info(monkeypatch, {
        "title": "Image post", "thumbnail": "https://example.com/image.jpg",
        "formats": formats,
    })
    package = InstagramDriver().extract("https://instagram.com/p/abc/", audio_only=audio_only)
    assert len(package.assets) == 1
    asset = package.primary_asset
    assert asset.filename == "content.jpg"
    assert asset.url == "https://example.com/image.jpg"
    assert asset.download_strategy == "http"
    assert asset.download_options == {}
    assert asset.expected_size is None
    assert asset.headers == {"User-Agent": "Mozilla/5.0"}
    assert package.metadata["author"] == {"id": "", "name": "Instagram User"}


def _instagram_photo_messages():
    post = {
        "post_shortcode": "BoHk1haB5tM", "post_id": 1880000000000000000,
        "count": 5, "description": "Five public photos " * 5,
        "username": "creator", "user": {"id": 123, "username": "creator"},
        "date": "2018-09-24 12:00:00",
    }
    messages = [[2, post.copy()]]
    for num, ext in [(5, "gif"), (2, "jpeg"), (4, "webp"), (1, "jpg"), (3, "png")]:
        url = f"https://scontent.cdninstagram.com/photo_{num}.{ext}?signed=public"
        messages.append([3, url, {**post, "num": num, "extension": ext, "display_url": url}])
    return messages


def _mock_instagram_gallery(monkeypatch, messages=None, **result):
    response = {"returncode": 0, "stdout": json.dumps(messages), "stderr": "", **result}
    run = MagicMock(return_value=MagicMock(**response))
    monkeypatch.setattr("drivers.social.instagram.subprocess.run", run)
    return run


def test_instagram_gallery_empty_media_urls_and_authorized_cookie(monkeypatch, tmp_path):
    messages = _instagram_photo_messages()
    for message in messages:
        message[-1].update(video_url=None, audio_url="")
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("DA_INSTAGRAM_COOKIE_FILE", str(cookie_file))
    run = _mock_instagram_gallery(monkeypatch, messages)
    package = InstagramDriver()._extract_photos(
        "https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM",
    )
    assert len(package.assets) == 5
    command = run.call_args.args[0]
    assert command[command.index("--cookies") + 1] == str(cookie_file)
    assert str(cookie_file) not in str(package.metadata)


def test_instagram_gallery_extracts_complete_ordered_five_photos(monkeypatch):
    messages = _instagram_photo_messages()
    messages.append(messages[2])  # Exact duplicates are harmless, not extra images.
    run = _mock_instagram_gallery(monkeypatch, messages)
    package = InstagramDriver()._extract_photos(
        "https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM",
    )
    assert package.platform == "instagram"
    assert package.original_url == "https://www.instagram.com/p/BoHk1haB5tM/"
    assert [a.filename for a in package.assets] == [
        "content.jpg", "image_02.jpeg", "image_03.png", "image_04.webp", "image_05.gif",
    ]
    assert [a.file_type for a in package.assets] == ["primary"] + ["companion"] * 4
    assert all(a.download_strategy == "http" and not a.download_options for a in package.assets)
    assert all(a.headers == {"User-Agent": "Mozilla/5.0"} for a in package.assets)
    assert package.metadata == {
        "title": messages[0][1]["description"][:60].strip(),
        "original_url": package.original_url,
        "author": {"id": 123, "name": "creator"},
        "created_at": "2018-09-24 12:00:00",
        "metrics": {"image_count": 5},
        "sidecar_text": messages[0][1]["description"],
    }
    assert package.title == package.metadata["title"]
    run.assert_called_once_with([
        sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-input",
        "--dump-json", "--retries", "0", "--http-timeout", "15",
        package.original_url,
    ], capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate_num", "duplicate_url", "conflicting_duplicate", "wrong_shortcode",
    "wrong_count", "missing_count", "bool_num", "missing_directory",
])
def test_instagram_gallery_rejects_incomplete_or_conflicting_photos(monkeypatch, mutation):
    messages = _instagram_photo_messages()
    if mutation == "missing":
        messages.pop()
    elif mutation == "duplicate_num":
        messages[-1][-1]["num"] = 1
    elif mutation == "duplicate_url":
        messages[-1][1] = messages[1][1]
    elif mutation == "conflicting_duplicate":
        messages.append([3, "https://other.fbcdn.net/extra.png", messages[-1][-1].copy()])
    elif mutation == "wrong_shortcode":
        messages[-1][-1]["post_shortcode"] = "anotherPost"
    elif mutation == "wrong_count":
        messages[-1][-1]["count"] = 6
    elif mutation == "missing_count":
        del messages[0][-1]["count"]
    elif mutation == "bool_num":
        messages[-1][-1]["num"] = True
    else:
        messages.pop(0)
    run = _mock_instagram_gallery(monkeypatch, messages)
    with pytest.raises(ExtractionError):
        InstagramDriver()._extract_photos("https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM")
    assert run.call_count == 1


@pytest.mark.parametrize("url", [
    "http://scontent.cdninstagram.com/photo.jpg", "https://evil.example/photo.jpg",
    "https://cdninstagram.com.evil.example/photo.jpg", "https://evilcdninstagram.com/photo.jpg",
    "https://user:pass@scontent.cdninstagram.com/photo.jpg",
    "https://user@scontent.fbcdn.net/photo.jpg", "https://scontent.fbcdn.net:8443/photo.jpg",
    "https://scontent.fbcdn.net:bad/photo.jpg", "https://scontent.fbcdn.net/photo.jpg#fragment",
    "https://scontent.fbcdn.net/\nphoto.jpg", None, 123,
])
def test_instagram_gallery_rejects_unsafe_photo_urls(monkeypatch, url):
    messages = _instagram_photo_messages()
    messages[-1][1] = url
    _mock_instagram_gallery(monkeypatch, messages)
    with pytest.raises(ExtractionError, match="Unsafe"):
        InstagramDriver()._extract_photos("https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM")


@pytest.mark.parametrize("host", ["scontent.fbcdn.net", "scontent.cdninstagram.com:443"])
def test_instagram_gallery_accepts_allowed_https_hosts_and_user_metadata(monkeypatch, host):
    messages = _instagram_photo_messages()
    messages[-1][1] = f"https://{host}/photo.png"
    del messages[0][-1]["username"]
    _mock_instagram_gallery(monkeypatch, messages)
    package = InstagramDriver()._extract_photos("https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM")
    assert package.metadata["author"] == {"id": 123, "name": "creator"}


@pytest.mark.parametrize("extra", [
    {"video_url": "https://scontent.fbcdn.net/video.mp4"}, {"audio_url": "https://scontent.fbcdn.net/audio.m4a"},
    {"extension": "mp4"}, {"extension": "m4a"}, {"extension": None},
])
def test_instagram_gallery_rejects_mixed_media(monkeypatch, extra):
    messages = _instagram_photo_messages()
    messages[-1][-1].update(extra)
    _mock_instagram_gallery(monkeypatch, messages)
    with pytest.raises(ExtractionError, match="mixed video/photo"):
        InstagramDriver()._extract_photos("https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM")


@pytest.mark.parametrize("messages", [
    [[-1, "AbortExtraction", "login redirect"]],
    _instagram_photo_messages() + [[-1, "AbortExtraction", "login redirect"]],
    {}, [], [None], [[3, "https://scontent.fbcdn.net/a.jpg", None]], [[2]],
])
def test_instagram_gallery_rejects_error_messages_and_malformed_output(monkeypatch, messages):
    run = _mock_instagram_gallery(monkeypatch, messages)
    with pytest.raises(ExtractionError):
        InstagramDriver()._extract_photos("https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM")
    assert run.call_count == 1


@pytest.mark.parametrize("result,match", [
    ({"returncode": 1, "stderr": "login redirect secret-value"}, "extraction failed"),
    ({"returncode": 1, "stderr": "No module named gallery_dl"}, "require gallery-dl"),
    ({"stdout": "not JSON"}, "Invalid JSON"),
])
def test_instagram_gallery_rejects_backend_failures_without_retry(monkeypatch, result, match):
    run = _mock_instagram_gallery(monkeypatch, _instagram_photo_messages(), **result)
    with pytest.raises(ExtractionError, match=match) as exc:
        InstagramDriver()._extract_photos("https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM")
    assert "secret-value" not in str(exc.value)
    assert run.call_count == 1


@pytest.mark.parametrize("error,match", [
    (subprocess.TimeoutExpired("gallery_dl", 60), "timed out"),
    (OSError("unavailable"), "Could not start"),
])
def test_instagram_gallery_timeout_or_start_failure_does_not_retry(monkeypatch, error, match):
    run = _mock_instagram_gallery(monkeypatch)
    run.side_effect = error
    with pytest.raises(ExtractionError, match=match):
        InstagramDriver()._extract_photos("https://www.instagram.com/p/BoHk1haB5tM/", "BoHk1haB5tM")
    assert run.call_count == 1


@pytest.mark.parametrize("error", ["No video formats found", "No video could be found"])
def test_instagram_only_explicit_no_video_uses_gallery(monkeypatch, error):
    factory, ydl = _mock_youtube_info(monkeypatch, None)
    ydl.extract_info.side_effect = Exception(error)
    run = _mock_instagram_gallery(monkeypatch, _instagram_photo_messages())
    package = InstagramDriver().extract("https://instagram.com/p/BoHk1haB5tM/?img_index=3")
    assert len(package.assets) == 5
    assert factory.call_count == ydl.extract_info.call_count == run.call_count == 1


@pytest.mark.parametrize("error", [
    "No video found", "does not contain a video", "backend failed", "timeout",
    *[f"No video formats found: {word} secret-value" for word in (
        "login", "log in", "sign in", "authentication", "cookie", "token", "401", "403",
        "429", "rate limit", "too many requests", "forbidden", "unauthorized", "captcha", "challenge",
    )],
])
def test_instagram_auth_or_other_errors_never_enter_gallery(monkeypatch, error):
    _, ydl = _mock_youtube_info(monkeypatch, None)
    ydl.extract_info.side_effect = Exception(error)
    fallback = MagicMock()
    monkeypatch.setattr(InstagramDriver, "_extract_photos", fallback)
    with pytest.raises(ExtractionError) as exc:
        InstagramDriver().extract("https://instagram.com/p/BoHk1haB5tM/")
    assert "secret-value" not in str(exc.value)
    fallback.assert_not_called()
    assert ydl.extract_info.call_count == 1


@pytest.mark.parametrize("info", [
    {"url": "https://example.com/video.mp4"},
    {"_type": "playlist", "entries": [{"url": "https://example.com/video.mp4"}]},
])
def test_instagram_video_and_playlist_never_enter_gallery(monkeypatch, info):
    _mock_youtube_info(monkeypatch, info)
    fallback = MagicMock()
    monkeypatch.setattr(InstagramDriver, "_extract_photos", fallback)
    if "entries" in info:
        with pytest.raises(ExtractionError, match="single video"):
            InstagramDriver().extract("https://instagram.com/p/BoHk1haB5tM/")
    else:
        assert InstagramDriver().extract("https://instagram.com/p/BoHk1haB5tM/").primary_asset.download_strategy == "ytdlp"
    fallback.assert_not_called()


def test_weibo_driver_can_handle():
    driver = WeiboDriver()
    assert driver.can_handle("https://weibo.com/1234567890/O5xxxxxxx")
    assert driver.can_handle("https://m.weibo.cn/detail/4999999999999999")
    assert driver.can_handle("https://weibo.cn/status/4999999999999999")
    assert not driver.can_handle("https://pan.baidu.com/s/1xxxx")

def _weibo_gallery_messages():
    status = {"id": 4409545658754086, "mblogid": "I40kdAJkW", "count": 9,
              "text": "<p>九张图片<br>公开正文</p>",
              "user": {"id": 2909128931, "screen_name": "公开作者"},
              "date": "2019-08-27 12:00:00"}
    return [[2, status]] + [
        [3, f"https://wx3.sinaimg.cn/large/photo{num}.jpg",
         {"num": num, "type": "orj360", "extension": "jpg", "status": status}]
        for num in range(1, 10)
    ]


def _mock_weibo_gallery(monkeypatch, messages=None, **kwargs):
    result = dict(returncode=0, stderr="", stdout=json.dumps(
        _weibo_gallery_messages() if messages is None else messages))
    result.update(kwargs)
    run = MagicMock(return_value=subprocess.CompletedProcess([], **result))
    monkeypatch.setattr("drivers.social.weibo.subprocess.run", run)
    return run


def _mock_weibo_mobile(monkeypatch, status=200, payload=None):
    response = MagicMock(status_code=status)
    response.json.return_value = payload if payload is not None else {"ok": 0}
    session = MagicMock()
    session.get.return_value = response
    monkeypatch.setattr("drivers.social.weibo.requests.Session", MagicMock(return_value=session))
    monkeypatch.setattr("drivers.social.weibo.credentials_manager.get_credential", MagicMock(return_value=""))
    monkeypatch.setattr(WeiboDriver, "_mint_visitor_cookie", lambda self: "")
    return session


@pytest.mark.parametrize("weibo_id", ["4409545658754086", "I40kdAJkW"])
def test_weibo_nine_photos_before_video(monkeypatch, weibo_id):
    _mock_weibo_mobile(monkeypatch)
    messages = _weibo_gallery_messages()
    messages.append(messages[1])  # Repeated identical rows must not duplicate assets.
    run = _mock_weibo_gallery(monkeypatch, messages)
    factory, _ = _mock_youtube_info(monkeypatch, None)
    package = WeiboDriver().extract(f"https://weibo.com/2909128931/{weibo_id}")
    assert len(package.assets) == package.metadata["image_count"] == 9
    assert package.assets[0].filename == "content.jpg"
    assert package.assets[0].file_type == "primary"
    assert [a.filename for a in package.assets[1:]] == [f"image_{i:02d}.jpg" for i in range(2, 10)]
    assert all(a.file_type == "companion" for a in package.assets[1:])
    assert all(a.headers == {"Referer": "https://weibo.com"} for a in package.assets)
    assert package.metadata["author"]["name"] == "公开作者"
    assert package.metadata["created_at"] == "2019-08-27 12:00:00"
    assert "公开正文" in package.metadata["sidecar_text"]
    assert "<p>" not in package.title
    json.dumps(package.metadata)
    factory.assert_not_called()
    run.assert_called_once_with(
        [sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-input", "--dump-json",
         "--retries", "0", "--http-timeout", "15", f"https://m.weibo.cn/detail/{weibo_id}"],
        capture_output=True, text=True, timeout=60, shell=False,
    )


@pytest.mark.parametrize("mutation", ["missing", "count", "num", "conflict", "duplicate_url", "identity", "nested_identity", "nested_count"])
def test_weibo_gallery_rejects_incomplete_or_wrong_album(monkeypatch, mutation):
    messages = _weibo_gallery_messages()
    if mutation == "missing":
        messages.pop()
    elif mutation == "count":
        messages[0][1]["count"] = 8
    elif mutation == "num":
        messages[-1][2]["num"] = 10
    elif mutation == "conflict":
        messages[-1][2]["num"] = 1
    elif mutation == "duplicate_url":
        messages[-1][1] = messages[1][1]
    elif mutation == "identity":
        messages[0][1]["id"] = 123
    elif mutation == "nested_count":
        messages[-1][2]["status"] = dict(messages[0][1], count=10)
    else:
        messages[-1][2]["status"] = {"id": 123}
    _mock_weibo_gallery(monkeypatch, messages)
    with pytest.raises(ExtractionError):
        WeiboDriver()._extract_photos("https://m.weibo.cn/detail/4409545658754086", "4409545658754086")


@pytest.mark.parametrize("url", [
    "http://wx3.sinaimg.cn/large/photo1.jpg", "https://evil.test/large/photo1.jpg",
    "https://wx3.sinaimg.cn.evil.test/large/photo1.jpg", "file:///large/photo1.jpg",
    "https://user:pass@wx3.sinaimg.cn/large/photo1.jpg", "https://wx3.sinaimg.cn:123/large/photo1.jpg",
    "https://wx3.sinaimg.cn/thumbnail/photo1.jpg", "https://wx3.sinaimg.cn/large/../photo1.jpg",
    "https://wx3.sinaimg.cn/large/%2e%2e%2fphoto1.jpg", "https://wx3.sinaimg.cn/large/photo1.mp4",
])
def test_weibo_gallery_rejects_unsafe_image_urls(monkeypatch, url):
    messages = _weibo_gallery_messages()
    messages[1][1] = url
    _mock_weibo_gallery(monkeypatch, messages)
    with pytest.raises(ExtractionError, match="Unsafe"):
        WeiboDriver()._extract_photos("https://m.weibo.cn/detail/4409545658754086", "4409545658754086")


@pytest.mark.parametrize("mixed", [True, False])
def test_weibo_gallery_non_images_preserve_video_fallback(monkeypatch, mixed):
    _mock_weibo_mobile(monkeypatch)
    messages = _weibo_gallery_messages()
    messages[-1][1] = "https://video.weibo.com/video.mp4"
    messages[-1][2]["extension"] = "mp4"
    if not mixed:
        messages = [messages[0], messages[-1]]
    run = _mock_weibo_gallery(monkeypatch, messages)
    _, ydl = _mock_youtube_info(monkeypatch, {"url": "https://video.weibo.com/video.mp4", "title": "Video"})
    package = WeiboDriver().extract("https://weibo.com/2909128931/4409545658754086")
    assert package.primary_asset.filename == "content.mp4"
    assert len(package.assets) == 1
    assert ydl.extract_info.call_count == run.call_count == 1


@pytest.mark.parametrize("status", [401, 403, 429])
def test_weibo_mobile_access_errors_do_not_switch_backend(monkeypatch, status):
    _mock_weibo_mobile(monkeypatch, status=status)
    run = _mock_weibo_gallery(monkeypatch)
    factory, _ = _mock_youtube_info(monkeypatch, None)
    with pytest.raises(ExtractionError, match="authentication/access"):
        WeiboDriver().extract("https://weibo.com/2909128931/4409545658754086")
    run.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize("stderr", ["login required secret-value", "HTTP 429 secret-value", "403 Forbidden", "cookie expired"])
def test_weibo_gallery_access_errors_do_not_retry_or_switch(monkeypatch, stderr):
    _mock_weibo_mobile(monkeypatch)
    run = _mock_weibo_gallery(monkeypatch, returncode=1, stderr=stderr)
    factory, _ = _mock_youtube_info(monkeypatch, None)
    with pytest.raises(ExtractionError, match="authentication/access") as exc:
        WeiboDriver().extract("https://weibo.com/2909128931/4409545658754086")
    assert "secret-value" not in str(exc.value)
    assert run.call_count == 1
    factory.assert_not_called()


@pytest.mark.parametrize("result", [
    {"returncode": 1, "stderr": "backend failed secret-value"},
    {"stdout": "invalid secret-value"}, {"stdout": "{}"},
])
def test_weibo_gallery_invalid_responses_fail_closed(monkeypatch, result):
    run = _mock_weibo_gallery(monkeypatch, **result)
    with pytest.raises(ExtractionError) as exc:
        WeiboDriver()._extract_photos("https://m.weibo.cn/detail/4409545658754086", "4409545658754086")
    assert "secret-value" not in str(exc.value)
    assert run.call_count == 1


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("gallery_dl", 60), OSError("unavailable")])
def test_weibo_gallery_process_errors_do_not_retry(monkeypatch, error):
    run = _mock_weibo_gallery(monkeypatch)
    run.side_effect = error
    with pytest.raises(ExtractionError):
        WeiboDriver()._extract_photos("https://m.weibo.cn/detail/4409545658754086", "4409545658754086")
    assert run.call_count == 1


@pytest.mark.parametrize("video", [True, False])
def test_weibo_mobile_media_stays_first(monkeypatch, video):
    data = {"text": "Mobile post", "user": {"screen_name": "Author"}}
    if video:
        data["page_info"] = {"media_info": {"stream_url_hd": "https://video.weibo.com/video.mp4"}}
    else:
        data["pics"] = [{"large": {"url": "https://wx3.sinaimg.cn/large/photo.jpg"}}]
    _mock_weibo_mobile(monkeypatch, payload={"ok": 1, "data": data})
    run = _mock_weibo_gallery(monkeypatch)
    factory, _ = _mock_youtube_info(monkeypatch, None)
    package = WeiboDriver().extract("https://weibo.com/2909128931/4409545658754086")
    assert package.primary_asset.filename == ("content.mp4" if video else "content.jpg")
    run.assert_not_called()
    factory.assert_not_called()


def test_weibo_empty_gallery_returns_none(monkeypatch):
    _mock_weibo_gallery(monkeypatch, [])
    assert WeiboDriver()._extract_photos("https://m.weibo.cn/detail/4409545658754086", "4409545658754086") is None


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
