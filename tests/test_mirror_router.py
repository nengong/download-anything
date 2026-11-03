"""
Unit tests for MirrorRouter
"""
from core.mirror_router import MirrorRouter

def test_github_mirror_resolution():
    raw_url = "https://raw.githubusercontent.com/torvalds/linux/master/README"
    mirrors = MirrorRouter.get_mirrors(raw_url)
    assert len(mirrors) > 0
    assert any("gh-proxy.com" in m for m in mirrors)
    assert any("ghfast.top" in m for m in mirrors)

def test_arxiv_mirror_resolution():
    arxiv_url = "https://arxiv.org/pdf/2310.06825.pdf"
    mirrors = MirrorRouter.get_mirrors(arxiv_url)
    assert len(mirrors) == 1
    assert "cn.arxiv.org" in mirrors[0]

def test_huggingface_mirror_resolution():
    hf_url = "https://huggingface.co/bert-base-uncased/resolve/main/config.json"
    mirrors = MirrorRouter.get_mirrors(hf_url)
    assert len(mirrors) == 1
    assert "hf-mirror.com" in mirrors[0]

def test_libgen_mirror_rotation():
    lg_url = "https://libgen.is/get.php?md5=70dbedfb04537d377cb093cdae645f37"
    mirrors = MirrorRouter.get_mirrors(lg_url)
    assert len(mirrors) > 0
    assert any("libgen.rs" in m or "libgen.st" in m for m in mirrors)
