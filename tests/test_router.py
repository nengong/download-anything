"""
Unit Tests for Smart Router and Dirty Input Cleaner
"""
import pytest
from core.router import Router, CleanInput
from core.exceptions import UrlNotSupportedError
from drivers.pan.lanzou import LanzouDriver
from drivers.pan.quark import QuarkDriver
from drivers.books.shadow_library import ShadowLibraryDriver

@pytest.fixture
def router():
    return Router([
        LanzouDriver(),
        QuarkDriver(),
        ShadowLibraryDriver(),
    ])

def test_clean_dirty_mobile_share_lanzou(router):
    dirty_text = (
        "【蓝奏云优质资源分享】\n"
        "点击链接直接下载：https://wwx.lanzoup.com/b0123456 \n"
        "访问密码：8888 赶快保存防止失效！"
    )
    driver, cleaned = router.route(dirty_text)
    assert driver.name == "lanzou"
    assert cleaned.url == "https://wwx.lanzoup.com/b0123456"
    assert cleaned.password == "8888"

def test_clean_quark_share_with_passcode(router):
    dirty_text = (
        "我用夸克网盘分享了「爱比克泰德.pdf」，点击链接即可保存。\n"
        "打开【夸克APP】，无需下载极速播放，链接：https://pan.quark.cn/s/a9f0e1b2c3d4 \n"
        "提取码：xyz9"
    )
    driver, cleaned = router.route(dirty_text)
    assert driver.name == "quark"
    assert cleaned.url == "https://pan.quark.cn/s/a9f0e1b2c3d4"
    assert cleaned.password == "xyz9"

def test_clean_url_with_query_param_password(router):
    url = "https://pan.lanzou.com/i12345?pwd=pass"
    driver, cleaned = router.route(url)
    assert driver.name == "lanzou"
    assert cleaned.url == "https://pan.lanzou.com/i12345?pwd=pass"
    assert cleaned.password == "pass"

def test_shadow_library_md5_input(router):
    raw_md5 = "70dbedfb04537d377cb093cdae645f37"
    driver, cleaned = router.route(raw_md5)
    assert driver.name == "shadow_library"
    assert "70dbedfb04537d377cb093cdae645f37" in cleaned.url

def test_annas_archive_url(router):
    url = "https://annas-archive.gl/md5/70dbedfb04537d377cb093cdae645f37"
    driver, cleaned = router.route(url)
    assert driver.name == "shadow_library"
    assert cleaned.url == url

def test_unsupported_url(router):
    with pytest.raises(UrlNotSupportedError):
        router.route("https://unsupported-unknown-domain-xyz.com/file")
