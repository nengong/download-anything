"""
Driver Registry and Dynamic Discovery
"""
from typing import List
from drivers.base import BaseDriver
from drivers.pan.lanzou import LanzouDriver
from drivers.pan.quark import QuarkDriver
from drivers.books.shadow_library import ShadowLibraryDriver
from drivers.social.xhs import XiaohongshuDriver
from drivers.social.douyin import DouyinDriver
from drivers.social.bilibili import BilibiliDriver
from drivers.dev.github_dir import GitHubDirDriver
from drivers.audio.xiaoyuzhou import XiaoyuzhouDriver
from drivers.docs.wechat import WeChatDriver

def get_default_drivers() -> List[BaseDriver]:
    """Return an instantiated list of all active drivers in priority order."""
    return [
        LanzouDriver(),
        QuarkDriver(),
        ShadowLibraryDriver(),
        XiaohongshuDriver(),
        DouyinDriver(),
        BilibiliDriver(),
        GitHubDirDriver(),
        XiaoyuzhouDriver(),
        WeChatDriver(),
    ]
