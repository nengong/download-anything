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
        }
    ]

    # When user converses in Chinese -> Chinese prioritized
    ranked_zh = driver._rank_candidates(candidates, "三体", preferred_lang="zh")
    assert ranked_zh[0]["language"] == "Chinese"
    assert ranked_zh[0]["md5"] == "22222222222222222222222222222222"

    # When user converses in English -> English prioritized
    ranked_en = driver._rank_candidates(candidates, "Three-Body Problem", preferred_lang="en")
    assert ranked_en[0]["language"] == "English"
    assert ranked_en[0]["md5"] == "11111111111111111111111111111111"

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
