"""Backward-compatible launcher for the DroidFleet application."""

from app.bootstrap import ensure_runtime_layout, print_first_run_banner

ensure_runtime_layout()
print_first_run_banner()

from app.main import AndroidController, main

__all__ = ["AndroidController", "main"]


if __name__ == "__main__":
    main()
