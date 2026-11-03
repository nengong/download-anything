"""
Unit Tests for Phase 4 Drivers:
YouTube, Twitter/X, Instagram, Weibo, Apple Podcasts, Novel, DOI
"""
import pytest
from drivers.social.youtube import YouTubeDriver
from drivers.social.twitter import TwitterDriver
from drivers.social.instagram import InstagramDriver
from drivers.social.weibo import WeiboDriver
from drivers.audio.apple_podcasts import ApplePodcastsDriver
from drivers.books.novel import NovelDriver
from drivers.books.doi import DOIDriver

def test_youtube_driver_can_handle():
    driver = YouTubeDriver()
    assert driver.can_handle("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert driver.can_handle("https://youtu.be/dQw4w9WgXcQ")
    assert driver.can_handle("https://www.youtube.com/shorts/abcdef12345")
    assert not driver.can_handle("https://v.douyin.com/abcde/")

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

def test_doi_driver_can_handle():
    driver = DOIDriver()
    assert driver.can_handle("https://doi.org/10.1038/nature12373")
    assert driver.can_handle("doi:10.1360/SSV-2023-0180")
    assert driver.can_handle("10.1145/3372278.3390678")
    assert not driver.can_handle("https://youtube.com/watch?v=123")
