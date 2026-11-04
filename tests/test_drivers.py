"""
Unit Tests for Drivers (Lanzou, Quark, Shadow Library)
"""
from unittest.mock import MagicMock
import pytest
from drivers.pan.lanzou import LanzouDriver
from drivers.pan.quark import QuarkDriver
from drivers.pan.baidu import BaiduDriver
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

def test_baidu_driver_can_handle():
    driver = BaiduDriver()
    assert driver.can_handle("https://pan.baidu.com/s/1xxxx")
    assert driver.can_handle("https://pan.baidu.com/share/init?surl=yyyy")
    assert not driver.can_handle("https://pan.quark.cn/s/12345")

def test_baidu_driver_missing_cookie_raises(monkeypatch):
    driver = BaiduDriver()
    monkeypatch.setattr("core.credentials.credentials_manager.get_credential", lambda *args: None)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "errno": 0,
        "data": {
            "share_id": 12345,
            "uk": 67890,
            "list": [{"fs_id": 111, "server_filename": "test.pdf", "size": 1024, "isdir": 0}]
        }
    }
    monkeypatch.setattr("requests.Session.get", lambda *args, **kwargs: mock_resp)
    with pytest.raises(AuthenticationRequiredError) as exc_info:
        driver.extract("https://pan.baidu.com/s/1xxxx")
    assert "BDUSS" in str(exc_info.value)

def test_shadow_library_can_handle():
    driver = ShadowLibraryDriver()
    assert driver.can_handle("70dbedfb04537d377cb093cdae645f37")
    assert driver.can_handle("md5:70dbedfb04537d377cb093cdae645f37")
    assert driver.can_handle("https://annas-archive.gl/md5/70dbedfb04537d377cb093cdae645f37")
    assert driver.can_handle("http://libgen.la/ads.php?md5=70dbedfb04537d377cb093cdae645f37")
    assert driver.can_handle("book:哲学谈话录")
    assert driver.can_handle("三体")
    assert driver.can_handle("Thinking, Fast and Slow")
    assert not driver.can_handle("https://pan.quark.cn/s/123")
    assert not driver.can_handle("10.1038/s41586-020-2649-2")
    assert not driver.can_handle("doi:10.1038/s41586-020-2649-2")
    assert not driver.can_handle("2310.06825")
    assert not driver.can_handle("9nt1r1c2hh7j")
    assert not driver.can_handle("com.termux")
    assert not driver.can_handle("apk:com.termux")

def test_shadow_library_language_ranking():
    driver = ShadowLibraryDriver()
    candidates = [
        {
            "title": "The Three-Body Problem",
            "author": "Cixin Liu",
            "language": "English",
            "extension": "epub",
            "year": "2014",
            "md5": "11111111111111111111111111111111"
        },
        {
            "title": "三体全集",
            "author": "刘慈欣",
            "language": "Chinese",
            "extension": "epub",
            "year": "2010",
            "md5": "22222222222222222222222222222222"
        },
        {
            "title": "三体 (日本語版)",
            "author": "劉慈欣",
            "language": "Japanese",
            "extension": "epub",
            "year": "2019",
            "md5": "33333333333333333333333333333333"
        },
        {
            "title": "Die drei Sonnen",
            "author": "Cixin Liu",
            "language": "German",
            "extension": "epub",
            "year": "2017",
            "md5": "44444444444444444444444444444444"
        },
        {
            "title": "El problema de los tres cuerpos",
            "author": "Cixin Liu",
            "language": "Spanish",
            "extension": "epub",
            "year": "2016",
            "md5": "55555555555555555555555555555555"
        }
    ]

    # Chinese prioritized
    ranked_zh = driver._rank_candidates(candidates, "三体", preferred_lang="zh")
    assert ranked_zh[0]["language"] == "Chinese"

    # English prioritized
    ranked_en = driver._rank_candidates(candidates, "Three-Body Problem", preferred_lang="en")
    assert ranked_en[0]["language"] == "English"

    # Japanese prioritized (via ISO code or Chinese name)
    ranked_ja = driver._rank_candidates(candidates, "三体", preferred_lang="ja")
    assert ranked_ja[0]["language"] == "Japanese"
    assert driver._rank_candidates(candidates, "三体", preferred_lang="日语")[0]["language"] == "Japanese"

    # German prioritized (via ISO 'de' matching LibGen 'German')
    ranked_de = driver._rank_candidates(candidates, "Die drei Sonnen", preferred_lang="de")
    assert ranked_de[0]["language"] == "German"

    # Spanish prioritized (via ISO 'es' matching LibGen 'Spanish')
    ranked_es = driver._rank_candidates(candidates, "El problema", preferred_lang="es")
    assert ranked_es[0]["language"] == "Spanish"

    # Script auto-detection when preferred_lang is None
    assert driver._normalize_language_pref(None, "ノルウェイの森") == "ja"
    assert driver._normalize_language_pref(None, "채식주의자") == "ko"
    assert driver._normalize_language_pref(None, "Война и мир") == "ru"
    assert driver._normalize_language_pref(None, "三体") == "zh"
    assert driver._normalize_language_pref(None, "Clean Code") == "en"

def test_shadow_library_extract_by_search(monkeypatch):
    driver = ShadowLibraryDriver()

    fake_candidates = [
        {
            "title": "哲学谈话录",
            "author": "爱比克泰德",
            "publisher": "商务印书馆",
            "year": "2018",
            "language": "Chinese",
            "extension": "epub",
            "md5": "87fdb2a976b23c856d7df949aa2b37fa"
        }
    ]
    monkeypatch.setattr(driver, "_search_libgen", lambda q: fake_candidates)

    from drivers.base import AssetPackage, TargetAsset
    fake_pkg = AssetPackage(
        title="哲学谈话录",
        platform=driver.name,
        assets=[
            TargetAsset(
                url="http://libgen.la/get.php?key=123",
                filename="哲学谈话录.epub",
                file_type="primary"
            )
        ],
        metadata={"md5": "87fdb2a976b23c856d7df949aa2b37fa"}
    )
    monkeypatch.setattr(driver, "_resolve_via_libgen", lambda md5: fake_pkg)

    pkg = driver.extract("哲学谈话录", preferred_lang="zh")
    assert pkg.title == "哲学谈话录"
    assert pkg.metadata["search_query"] == "哲学谈话录"
    assert pkg.metadata["preferred_lang"] == "zh"
    assert pkg.assets[0].filename == "哲学谈话录.epub"
    assert "基于对话语言设定优先级：中文" in pkg.raw_markdown
