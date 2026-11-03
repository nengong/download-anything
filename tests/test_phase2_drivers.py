"""
Unit Tests for Phase 2 Drivers (XHS, Douyin, Bilibili, GitHub)
"""
import pytest
from drivers.social.xhs import XiaohongshuDriver
from drivers.social.douyin import DouyinDriver
from drivers.social.bilibili import BilibiliDriver
from drivers.dev.github_dir import GitHubDirDriver

def test_xhs_driver_can_handle():
    driver = XiaohongshuDriver()
    assert driver.can_handle("http://xhslink.com/a/ABC123xyz")
    assert driver.can_handle("https://www.xiaohongshu.com/explore/654321abcdef")
    assert not driver.can_handle("https://v.douyin.com/123456/")

def test_xhs_bracket_parser():
    driver = XiaohongshuDriver()
    html = """
    <html><head><script>
    window.__INITIAL_STATE__ = {"noteData":{"data":{"noteData":{"title":"测试标题","desc":"测试正文","imageList":[{"fileId":"12345"}]}}}};
    </script></head><body></body></html>
    """
    state = driver._extract_initial_state(html)
    assert state is not None
    assert state["title"] == "测试标题"
    assert len(state["imageList"]) == 1

def test_douyin_driver_can_handle():
    driver = DouyinDriver()
    assert driver.can_handle("https://v.douyin.com/iABC123/")
    assert driver.can_handle("https://www.douyin.com/video/7123456789012345678")
    assert not driver.can_handle("https://www.bilibili.com/video/BV1xx411c7mD")

def test_bilibili_driver_can_handle():
    driver = BilibiliDriver()
    assert driver.can_handle("https://www.bilibili.com/video/BV1xx411c7mD")
    assert driver.can_handle("https://b23.tv/av123456")
    assert driver.can_handle("BV1xx411c7mD")
    assert not driver.can_handle("https://github.com/torvalds/linux")

def test_github_dir_can_handle():
    driver = GitHubDirDriver()
    assert driver.can_handle("https://github.com/torvalds/linux/tree/master/Documentation")
    assert driver.can_handle("https://github.com/psf/requests/blob/main/README.md")
    assert not driver.can_handle("https://pan.quark.cn/s/123")
