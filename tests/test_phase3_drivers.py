"""
Unit Tests for Phase 3 Drivers (Xiaoyuzhou Podcast & WeChat Official Account)
"""
from drivers.audio.xiaoyuzhou import XiaoyuzhouDriver
from drivers.docs.wechat import WeChatDriver

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
