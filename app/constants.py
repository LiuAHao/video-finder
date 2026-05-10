"""Constants used throughout the application."""

# Default User-Agent (Chrome)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Video file extensions
VIDEO_EXTENSIONS = {
    ".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".wmv",
    ".m4v", ".ts", ".f4v", ".vob", ".ogv", ".3gp", ".3g2",
}

# HLS extensions
HLS_EXTENSIONS = {".m3u8"}

# DASH extensions
DASH_EXTENSIONS = {".mpd"}

# Media content types
VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/webm",
    "video/x-flv",
    "video/x-msvideo",
    "video/quicktime",
    "video/x-matroska",
    "video/MP2T",
    "application/x-mpegURL",  # HLS
    "application/vnd.apple.mpegurl",  # HLS
    "application/dash+xml",  # DASH
}

# HLS content types
HLS_CONTENT_TYPES = {
    "application/x-mpegURL",
    "application/vnd.apple.mpegurl",
}

# DASH content types
DASH_CONTENT_TYPES = {
    "application/dash+xml",
}

# DRM indicators
DRM_INDICATORS = [
    "widevine",
    "playready",
    "fairplay",
    "ContentProtection",
    "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed",  # Widevine
    "urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95",  # PlayReady
    "urn:uuid:94ce86fb-07ff-4f43-adb8-93d2fa968ca2",  # FairPlay
]

# Temporary URL indicators
TEMPORARY_URL_INDICATORS = [
    "token=",
    "expires=",
    "sign=",
    "signature=",
    "t=",
    "e=",
    "se=",
    "st=",
    "sp=",
    "sig=",
]

# Common play button selectors
PLAY_BUTTON_SELECTORS = [
    "button[aria-label*='play']",
    "button[aria-label*='Play']",
    ".play-button",
    ".play-btn",
    "#play-button",
    "#play-btn",
    ".vjs-big-play-button",
    ".ytp-large-play-button",
    ".ytp-play-button",
    "[data-testid='play-button']",
    "video",
]

# Video source attributes in HTML
SOURCE_ATTRIBUTES = [
    "src",
    "data-src",
    "data-video-url",
    "data-url",
    "data-href",
    "source",
]

# Player config keys that might contain video URLs
PLAYER_CONFIG_KEYS = [
    "src",
    "file",
    "url",
    "source",
    "video_url",
    "videoUrl",
    "video_url",
    "stream_url",
    "streamUrl",
    "media_url",
    "mediaUrl",
    "hls",
    "dash",
    "mp4",
    "webm",
]

# Score weights for candidate ranking
SCORE_WEIGHTS = {
    "master_m3u8": 95,
    "regular_m3u8": 88,
    "direct_video": 82,
    "mpd": 80,
    "yt_dlp_with_formats": 74,
    "other": 40,
}

# Default download directory
DEFAULT_DOWNLOAD_DIR = "./downloads"

# Default database path
DEFAULT_DATABASE_PATH = "./data/video_finder.sqlite"

# Default server settings
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860

# Default wait seconds
DEFAULT_WAIT_SECONDS = 10

# Default concurrency
DEFAULT_CONCURRENCY = 8
