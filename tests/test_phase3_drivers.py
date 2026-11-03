"""
Unit Tests for Phase 3 Drivers (Xiaoyuzhou Podcast & WeChat Official Account)
"""
from drivers.audio.xiaoyuzhou import XiaoyuzhouDriver
from drivers.docs.wechat import WeChatDriver
from drivers.books.arxiv import ArxivDriver

def test_xiaoyuzhou_driver_can_handle():
    driver = XiaoyuzhouDriver()
    assert driver.can_handle("https://www.xiaoyuzhoufm.com/episode/6ae440bcc96c8942ec14b02f")
    assert driver.can_handle("http://xiaoyuzhoufm.com/episode/123456")
    assert not driver.can_handle("https://mp.weixin.qq.com/s/12345")

def test_wechat_driver_can_handle():
    driver = WeChatDriver()
    assert driver.can_handle("https://mp.weixin.qq.com/s/-yt4CT1BS6vcUDXkQwjCoQ")
    assert driver.can_handle("http://mp.weixin.qq.com/s?__biz=MzA4...")
    assert not driver.can_handle("https://v.douyin.com/123")

def test_arxiv_driver_can_handle():
    driver = ArxivDriver()
    assert driver.can_handle("https://arxiv.org/abs/2310.06825")
    assert driver.can_handle("https://arxiv.org/pdf/2310.06825.pdf")
    assert driver.can_handle("2310.06825")
    assert not driver.can_handle("https://github.com/torvalds/linux")
