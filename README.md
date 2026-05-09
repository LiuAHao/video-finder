# Video Finder

本地运行的网页视频发现与下载工具。输入视频播放页地址，通过 Playwright 嗅探网络请求，识别 HLS/DASH/直链视频资源，并调用 yt-dlp / ffmpeg 完成下载。

## 功能

- 🔍 **多策略嗅探**：网络请求监听、HTML 静态扫描、播放器配置提取、yt-dlp 页面解析
- 🎬 **多格式支持**：HLS `.m3u8`、DASH `.mpd`、视频直链 `.mp4 / .webm / .mkv` 等
- ⬇️ **灵活下载**：优先使用 yt-dlp，失败自动 fallback 到 ffmpeg / HTTP 直下
- 📊 **实时进度**：SSE 推送下载进度、速度、剩余时间
- 📝 **历史记录**：SQLite 持久化嗅探与下载记录
- 🌐 **Web UI**：浏览器访问，无需额外客户端

## 快速开始

### 环境要求

- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（系统级安装或 PATH 可访问）
- [ffmpeg](https://ffmpeg.org/)（可选，用于 HLS/DASH 流下载备用）

### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装项目依赖及命令行工具
pip install -e .

# 安装 Playwright Chromium
playwright install chromium
```

### 2. 配置

复制 `.env.example` 为 `.env`，按需修改：

```bash
cp .env.example .env
```

主要配置项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VIDEO_FINDER_DOWNLOAD_DIR` | `./downloads` | 下载保存目录 |
| `VIDEO_FINDER_DATABASE_PATH` | `./data/video_finder.sqlite` | SQLite 数据库路径 |
| `VIDEO_FINDER_HEADLESS` | `true` | 是否无头模式运行浏览器 |
| `VIDEO_FINDER_WAIT_SECONDS` | `10` | 嗅探等待时间（秒） |
| `VIDEO_FINDER_AUTO_CLICK` | `true` | 是否自动点击播放按钮 |
| `VIDEO_FINDER_DEFAULT_DOWNLOADER` | `ytdlp` | 默认下载器 |
| `VIDEO_FINDER_CONCURRENCY` | `8` | yt-dlp 并发分片数 |
| `VIDEO_FINDER_HOST` | `127.0.0.1` | 服务监听地址 |
| `VIDEO_FINDER_PORT` | `7860` | 服务监听端口 |

### 3. 启动

```bash
# 首先确保激活虚拟环境
source venv/bin/activate

# 启动服务端
python -m app.main

# 或使用 CLI
video-finder open
```

浏览器访问 [http://127.0.0.1:7860](http://127.0.0.1:7860)

## 使用说明

1. 在输入框粘贴视频播放页 URL
2. 调整嗅探等待时间（复杂页面建议 15～30 秒）
3. 点击**开始嗅探**，等待资源列表出现
4. 从候选列表中选择目标资源，点击**下载**
5. 在下载任务区查看进度，完成后点击打开文件

## 项目结构

```
video-finder/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理（pydantic-settings）
│   ├── constants.py         # 常量定义
│   ├── models.py            # SQLAlchemy ORM 模型
│   ├── schemas.py           # Pydantic 请求/响应 Schema
│   ├── cli.py               # Typer CLI
│   ├── db/
│   │   └── database.py      # 数据库初始化
│   ├── services/
│   │   ├── sniffer.py       # Playwright 嗅探核心
│   │   ├── extractor.py     # URL 提取器
│   │   ├── parser.py        # 流媒体解析（m3u8/mpd）
│   │   ├── downloader.py    # 下载任务管理
│   │   ├── progress.py      # SSE 进度推送
│   │   ├── storage.py       # 数据持久化
│   │   └── safety.py        # 安全过滤
│   ├── downloaders/
│   │   ├── base.py          # 下载器基类
│   │   ├── ytdlp.py         # yt-dlp 封装
│   │   ├── ffmpeg.py        # ffmpeg 封装
│   │   └── http.py          # 普通 HTTP 下载
│   └── web/
│       ├── routes.py        # FastAPI 路由
│       └── templates/
│           └── index.html   # 单页 Web UI
├── data/                    # SQLite 数据库（运行时生成）
├── downloads/               # 默认下载目录
├── logs/                    # 日志目录
├── tests/                   # 单元测试
├── .env                     # 本地配置（不提交）
├── .env.example             # 配置示例
├── pyproject.toml
├── requirements.txt
└── PRD.md                   # 产品需求文档
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check app/
```

## 使用边界

- 仅用于自有素材、授权内容、公开视频、课程回放等**合法保存场景**
- 不支持绕过登录、付费墙、验证码、反爬机制或 DRM
- 不提供 DRM 解密、密钥破解、加密流绕过能力

## License

MIT
