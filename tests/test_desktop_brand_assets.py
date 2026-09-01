from pathlib import Path

from src.ui import asset_paths


def test_brand_assets_exist_in_source_checkout():
    root = asset_paths.asset_dir()
    for name in (
        "shanktuary_shield.png",
        "shanktuary_wordmark.png",
        "shanktuary_lockup.png",
    ):
        assert (root / name).is_file(), f"missing desktop brand asset: {name}"


def test_asset_dir_prefers_pyinstaller_bundle(monkeypatch, tmp_path):
    bundled = tmp_path / "assets"
    bundled.mkdir()
    (bundled / "shanktuary_shield.png").write_bytes(b"png")

    monkeypatch.setattr(asset_paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert asset_paths.asset_dir() == bundled
    assert Path(asset_paths.asset_path("shanktuary_shield.png")) == bundled / "shanktuary_shield.png"
