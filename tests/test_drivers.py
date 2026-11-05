"""
Unit Tests for Drivers (Lanzou, Quark, Shadow Library)
"""
from unittest.mock import MagicMock, patch
import pytest
from drivers.pan.lanzou import LanzouDriver
from drivers.pan.quark import QuarkDriver
from drivers.pan.baidu import BaiduDriver
from drivers.books.shadow_library import ShadowLibraryDriver
from core.exceptions import AuthenticationRequiredError, CloudDriveError, ExtractionError

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

def quark_response(data, status=200):
    response = MagicMock()
    response.json.return_value = {"status": status, "data": data}
    return response


def quark_file():
    return {"fid": "source-file", "file_name": "first.exe", "size": 123,
            "dir": False, "file": True, "share_fid_token": "file-token"}


@pytest.mark.parametrize("nested", [False, True])
def test_quark_token_detail_and_save_payload(nested):
    driver = QuarkDriver()
    events = []
    listings = [quark_response({"list": [quark_file()]})]
    if nested:
        listings.insert(0, quark_response({"list": [
            {"fid": "source-folder", "file_name": "folder", "dir": True, "file": False}]}))

    def get(url, **kwargs):
        events.append("detail")
        return listings.pop(0)

    def post(url, **kwargs):
        if "/token?" in url:
            events.append("token")
            return quark_response({"stoken": "share-token"})
        if "/save?" in url:
            events.append("save")
            return quark_response({"task_id": "task"})
        if "/download?" in url:
            return quark_response([{"download_url": "https://example.invalid/file"}])
        pytest.fail("Unexpected Quark write endpoint")

    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch("drivers.pan.quark.requests.get", side_effect=get) as detail, \
         patch("drivers.pan.quark.requests.post", side_effect=post) as posts, \
         patch.object(driver, "_get_or_create_temp_folder", return_value="owned"), \
         patch.object(driver, "_poll_task_completion", return_value="saved"):
        package = driver.extract("https://pan.quark.cn/s/demo", password="code")
    assert driver.API_BASE == "https://drive-h.quark.cn/1/clouddrive"
    assert events == (["token", "detail", "detail", "save"] if nested else ["token", "detail", "save"])
    assert posts.call_args_list[0].kwargs["json"] == {"pwd_id": "demo", "passcode": "code"}
    assert detail.call_args_list[0].kwargs["params"] == {
        "pr": "ucpro", "fr": "pc", "pwd_id": "demo", "stoken": "share-token",
        "pdir_fid": "0", "_page": 1, "_size": 50,
    }
    parent = "source-folder" if nested else "0"
    assert detail.call_args.kwargs["params"]["pdir_fid"] == parent
    assert posts.call_args_list[1].kwargs["json"] == {
        "pwd_id": "demo", "passcode": "code", "stoken": "share-token",
        "fid_list": ["source-file"], "fid_token_list": ["file-token"],
        "to_pdir_fid": "owned", "pdir_fid": parent, "scene": "link",
    }
    assert package.assets[0].filename == "first.exe"
    assert package.context["owned_temp_dir"] == "owned"
    assert package.assets[0].headers["Cookie"] == "DUMMY"


def test_quark_cleanup_uses_current_delete_payload():
    from drivers.base import AssetPackage
    driver = QuarkDriver()
    response = quark_response({"finish": True})
    package = AssetPackage(title="test", platform="quark", context={
        "owned_temp_dir": "owned", "headers": {"Cookie": "DUMMY"}})
    with patch("drivers.pan.quark.requests.post", return_value=response) as post:
        driver.cleanup(package)
    assert post.call_args.kwargs["json"] == {
        "action_type": 1, "filelist": ["owned"], "exclude_fids": []}


@pytest.mark.parametrize("token_data,status,error", [
    ({}, 200, ExtractionError), ({}, 400, CloudDriveError),
])
def test_quark_missing_share_token_stops_before_detail(token_data, status, error):
    driver = QuarkDriver()
    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch("drivers.pan.quark.requests.post", return_value=quark_response(token_data, status)) as post, \
         patch("drivers.pan.quark.requests.get") as get, \
         patch.object(driver, "_get_or_create_temp_folder") as create:
        with pytest.raises(error, match="token"):
            driver.extract("https://pan.quark.cn/s/demo", inspect_only=True)
    post.assert_called_once()
    get.assert_not_called()
    create.assert_not_called()


@pytest.mark.parametrize("missing", ["fid", "share_fid_token"])
def test_quark_missing_file_token_or_fid_never_writes(missing):
    item = quark_file()
    del item[missing]
    driver = QuarkDriver()
    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch("drivers.pan.quark.requests.post", return_value=quark_response({"stoken": "share-token"})) as post, \
         patch("drivers.pan.quark.requests.get", return_value=quark_response({"list": [item]})), \
         patch.object(driver, "_get_or_create_temp_folder") as create:
        with pytest.raises(ExtractionError, match="fid or share_fid_token"):
            driver.extract("https://pan.quark.cn/s/demo")
    post.assert_called_once()
    create.assert_not_called()


@pytest.mark.parametrize("case,expected", [
    ("empty", "No actual files"), ("depth", "depth limit"),
    ("pages", "pagination limit"), ("requests", "request limit"),
    ("exhausted", "pagination exhausted"),
])
def test_quark_bounded_search_errors_never_write(case, expected):
    driver = QuarkDriver()
    driver.SHARE_PAGE_SIZE = 1
    driver.SHARE_MAX_PAGES = 2
    driver.SHARE_MAX_DEPTH = 1
    driver.SHARE_MAX_REQUESTS = 4
    directory = {"fid": "folder", "dir": True, "file": False}
    if case == "empty":
        pages = [quark_response({"list": []})]
    elif case == "depth":
        pages = [quark_response({"list": [directory]}), quark_response({"list": []}),
                 quark_response({"list": [{"fid": "deep", "dir": True}]}),
                 quark_response({"list": []})]
    else:
        pages = [quark_response({"list": [{"dir": False, "file": False}]})] * 2
        if case == "requests":
            driver.SHARE_MAX_REQUESTS = 1
        elif case == "exhausted":
            pages[1] = quark_response({"list": []})
    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch("drivers.pan.quark.requests.post", return_value=quark_response({"stoken": "share-token"})) as post, \
         patch("drivers.pan.quark.requests.get", side_effect=pages), \
         patch.object(driver, "_get_or_create_temp_folder") as create:
        with pytest.raises(ExtractionError, match=expected):
            driver.extract("https://pan.quark.cn/s/demo", inspect_only=True)
    post.assert_called_once()
    create.assert_not_called()


def test_quark_preflight_skips_empty_subdirectory_and_never_writes():
    driver = QuarkDriver()
    second_file = dict(quark_file(), fid="second-file", file_name="second.exe",
                       share_fid_token="second-token")
    pages = [quark_response({"list": [
        {"fid": "empty", "dir": True, "file": False},
        {"fid": "source-folder", "dir": True, "file": False}]}),
        quark_response({"list": []}),
        quark_response({"list": [quark_file(), second_file]})]
    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch("drivers.pan.quark.requests.post", return_value=quark_response({"stoken": "share-token"})) as post, \
         patch("drivers.pan.quark.requests.get", side_effect=pages) as get, \
         patch.object(driver, "_get_or_create_temp_folder") as create:
        package = driver.extract("https://pan.quark.cn/s/demo", inspect_only=True)
    assert package.assets[0].filename == "first.exe"
    assert package.assets[0].url == ""
    assert package.metadata["requires_transfer"] is True
    assert [call.kwargs["params"]["pdir_fid"] for call in get.call_args_list] == [
        "0", "empty", "source-folder"]
    post.assert_called_once()
    assert "/share/sharepage/token?" in post.call_args.args[0]
    create.assert_not_called()


def test_quark_pagination_finds_actual_file_after_empty_directory():
    driver = QuarkDriver()
    driver.SHARE_PAGE_SIZE = 1
    pages = [quark_response({"list": [{"fid": "empty", "dir": True}]}),
             quark_response({"list": [quark_file()]})]
    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch("drivers.pan.quark.requests.post", return_value=quark_response({"stoken": "share-token"})) as post, \
         patch("drivers.pan.quark.requests.get", side_effect=pages) as get:
        package = driver.extract("https://pan.quark.cn/s/demo", inspect_only=True)
    assert package.assets[0].filename == "first.exe"
    assert [call.kwargs["params"]["_page"] for call in get.call_args_list] == [1, 2]
    post.assert_called_once()


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
