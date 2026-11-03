"""
Driver Registry and Dynamic Discovery
"""
from typing import List
from drivers.base import BaseDriver
from drivers.pan.lanzou import LanzouDriver
from drivers.pan.quark import QuarkDriver
from drivers.pan.baidu import BaiduDriver
from drivers.books.shadow_library import ShadowLibraryDriver
from drivers.books.arxiv import ArxivDriver
from drivers.books.doi import DOIDriver
from drivers.books.novel import NovelDriver
from drivers.social.xhs import XiaohongshuDriver
from drivers.social.douyin import DouyinDriver
from drivers.social.bilibili import BilibiliDriver
from drivers.social.youtube import YouTubeDriver
from drivers.social.twitter import TwitterDriver
from drivers.social.instagram import InstagramDriver
from drivers.social.weibo import WeiboDriver
from drivers.dev.github_dir import GitHubDirDriver
from drivers.audio.xiaoyuzhou import XiaoyuzhouDriver
from drivers.audio.apple_podcasts import ApplePodcastsDriver
from drivers.docs.wechat import WeChatDriver

def get_default_drivers() -> List[BaseDriver]:
    """Return an instantiated list of all active drivers in priority order."""
    return [
        LanzouDriver(),
        QuarkDriver(),
        BaiduDriver(),
        ShadowLibraryDriver(),
        ArxivDriver(),
        DOIDriver(),
        NovelDriver(),
        XiaohongshuDriver(),
        DouyinDriver(),
        BilibiliDriver(),
        YouTubeDriver(),
        TwitterDriver(),
        InstagramDriver(),
        WeiboDriver(),
        GitHubDirDriver(),
        XiaoyuzhouDriver(),
        ApplePodcastsDriver(),
        WeChatDriver(),
    ]
