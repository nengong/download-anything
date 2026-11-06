import pytest

from core.credentials import credentials_manager


@pytest.mark.parametrize("platform", ["baidu", "quark"])
def test_cookie_environment_alias_and_precedence(monkeypatch, platform):
    prefixed = f"DA_{platform.upper()}_COOKIE"
    alias = f"{platform.upper()}_COOKIE"
    monkeypatch.setenv(alias, " alias-cookie ")
    assert credentials_manager.get_credential(platform) == "alias-cookie"
    monkeypatch.setenv(prefixed, " preferred-cookie ")
    assert credentials_manager.get_credential(platform) == "preferred-cookie"
    monkeypatch.setenv(prefixed, "  ")
    assert credentials_manager.get_credential(platform) == "alias-cookie"


def test_unprefixed_alias_does_not_apply_to_other_keys(monkeypatch):
    monkeypatch.setenv("BAIDU_TOKEN", "unrelated-token")
    monkeypatch.delenv("DA_BAIDU_TOKEN", raising=False)
    assert credentials_manager.get_credential("baidu", "token") is None
    monkeypatch.setenv("DA_BAIDU_TOKEN", "preferred-token")
    assert credentials_manager.get_credential("baidu", "token") == "preferred-token"
