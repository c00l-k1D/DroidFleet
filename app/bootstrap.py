from __future__ import annotations

from pathlib import Path


def ensure_runtime_layout(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    for folder in (data_dir, data_dir / "logs", data_dir / "screenshots"):
        folder.mkdir(parents=True, exist_ok=True)
    return data_dir


def print_first_run_banner() -> None:
    data_dir = ensure_runtime_layout()
    print("\nDroidFleet ready for first launch.")
    print(f"Runtime workspace: {data_dir}")
    print("- logs: data/logs")
    print("- screenshots: data/screenshots")
    print("- accounts: data/accounts.enc")
    print("\nNext steps:")
    print("  1) ensure Android Platform Tools are installed and adb is on PATH")
    print("  2) run: py -3.13 farm_bot.py")
    print("  3) or open the GUI via: py -3.13 -m app.main")
    print()
