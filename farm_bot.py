"""Backward-compatible launcher for the DroidFleet application."""

from app.main import AndroidController, main

__all__ = ["AndroidController", "main"]


if __name__ == "__main__":
    main()
