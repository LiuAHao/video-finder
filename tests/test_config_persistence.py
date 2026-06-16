"""Tests for local config persistence behavior."""

from app.config import PROJECT_ROOT, Settings, resolve_project_path


def test_resolve_project_path_anchors_relative_paths_to_project_root():
    expected = str((PROJECT_ROOT / "downloads").resolve())
    assert resolve_project_path("downloads") == expected


def test_settings_normalize_env_paths(monkeypatch):
    monkeypatch.setenv("VIDEO_FINDER_DOWNLOAD_DIR", "custom-downloads")
    monkeypatch.setenv("VIDEO_FINDER_DATABASE_PATH", "custom-data/video_finder.sqlite")

    settings = Settings()

    assert settings.download_dir == str((PROJECT_ROOT / "custom-downloads").resolve())
    assert settings.database_path == str(
        (PROJECT_ROOT / "custom-data/video_finder.sqlite").resolve()
    )
