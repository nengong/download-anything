"""
Unit Tests for Drivers (Lanzou, Quark, Shadow Library)
"""
from unittest.mock import MagicMock
import pytest
from drivers.pan.lanzou import LanzouDriver
from drivers.pan.quark import QuarkDriver
from drivers.books.shadow_library import ShadowLibraryDriver
from core.exceptions import AuthenticationRequiredError, ExtractionError

def test_lanzou_driver_can_handle():
    driver = LanzouDriver()
    assert driver.can_handle("https://pan.lanzou.com/b0123456")
    assert driver.can_handle("https://wwx.lanzoup.com/abcdef")
    assert not driver.can_handle("https://pan.quark.cn/s/12345")

def test_quark_driver_can_handle():
    driver = QuarkDriver()
    assert driver.can_handle("https://pan.quark.cn/s/abcdef123456")
    assert not driver.can_handle("https://pan.baidu.com/s/12345")

def test_quark_driver_missing_cookie_raises(monkeypatch):
    driver = QuarkDriver()
    monkeypatch.setattr("core.credentials.credentials_manager.get_credential", lambda *args: None)
    with pytest.raises(AuthenticationRequiredError) as exc_info:
        driver.extract("https://pan.quark.cn/s/abcdef123456")
    assert "Quark Cloud Drive download requires authentication cookie" in str(exc_info.value)

def test_shadow_library_can_handle():
    driver = ShadowLibraryDriver()
    assert driver.can_handle("70dbedfb04537d377cb093cdae645f37")
    assert driver.can_handle("md5:70dbedfb04537d377cb093cdae645f37")
    assert driver.can_handle("https://annas-archive.gl/md5/70dbedfb04537d377cb093cdae645f37")
    assert driver.can_handle("http://libgen.la/ads.php?md5=70dbedfb04537d377cb093cdae645f37")
    assert not driver.can_handle("https://pan.quark.cn/s/123")
