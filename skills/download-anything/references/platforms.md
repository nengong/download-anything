# 平台适配状态

以下 27 个注册驱动均为**实验性平台适配**。当前工程回归覆盖安装、文件交付、安全边界和模拟平台响应；尚未完成统一的真实平台发布验收，不承诺无水印、最高画质、下载速度或长期可用性。

| 分类 | 驱动 | 限制 |
| --- | --- | --- |
| 文档 | feishu_doc、notion_public、web_article、wechat | 依赖返回 HTML；动态渲染、私密页、验证页可能提取失败或不完整 |
| 音乐 | music_163、spotify_apple、open_music、local_audio | 跨源音乐使用文本检索，不是声学指纹比对；可能匹配到不同版本。转码需 ffmpeg |
| 播客 | apple_podcasts、xiaoyuzhou | 取决于公开元数据和原音频地址可用性 |
| 网盘 | baidu、quark、lanzou | 百度/夸克实际下载会转存，预检不转存；目前优先处理分享中的第一个文件 |
| 社交 | youtube、twitter、instagram、weibo、xiaohongshu、douyin、bilibili | 登录、反爬、格式选择和字幕可用性因站点而异；YouTube 优先取含声画的 MP4，可能回退为单独视频流，字幕选择一个可用语言 |
| 图书/论文 | doi、shadow_library、novel、arxiv | 来源可用性与镜像会变化；shadow_library 支持书名/ISBN模糊检索（按用户对话语言优先匹配）与直链解析；不能保证指定书籍或论文一定有完整可下载版本 |
| 安装包 | ms_store、android_apk | 依赖目录服务返回候选；格式检查不等同于发布者签名认证 |
| 代码 | github | 实验性兼容驱动，排除于首发稳定承诺和目录验收门槛；优先使用已有 GitHub CLI/MCP。当前仅直接文件，不递归子目录 |

更换机器、平台登录态或发布版本后，需重新记录实际测试。未完成真实联调前，不能把模拟测试通过写成某个平台已验证可用。
