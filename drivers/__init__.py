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
from drivers.audio.music_163 import NetEaseMusicDriver
from drivers.audio.spotify_apple import SpotifyAppleMusicDriver
from drivers.audio.open_music import OpenMusicDriver
from drivers.audio.local_audio import LocalAudioDriver
from drivers.docs.wechat import WeChatDriver
from drivers.docs.web_article import WebArticleDriver
from drivers.docs.feishu import FeishuDocDriver
from drivers.docs.notion import NotionPublicDriver
from drivers.software.ms_store import MicrosoftStoreDriver
from drivers.software.apk import AndroidAPKDriver

def get_default_drivers() -> List[BaseDriver]:
    """Return an instantiated list of all active drivers in priority order."""
    return [
        LocalAudioDriver(),
        LanzouDriver(),
        QuarkDriver(),
        BaiduDriver(),
        NetEaseMusicDriver(),
        SpotifyAppleMusicDriver(),
        OpenMusicDriver(),
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
        FeishuDocDriver(),
        NotionPublicDriver(),
        WebArticleDriver(),
        MicrosoftStoreDriver(),
        AndroidAPKDriver(),
    ]
