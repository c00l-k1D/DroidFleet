from pathlib import Path
import os
import time

from agent import process


def test_roblox_command_uses_configured_environment(monkeypatch):
    monkeypatch.setenv("DROIDFLEET_ROBLOX", r"C:\Games\RobloxPlayerBeta.exe")
    assert process._process_command("DROIDFLEET_ROBLOX") == r"C:\Games\RobloxPlayerBeta.exe"


def test_roblox_command_finds_latest_standard_install(monkeypatch, tmp_path):
    versions = tmp_path / "Roblox" / "Versions"
    old = versions / "old"
    new = versions / "new"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    old_exe = old / "RobloxPlayerBeta.exe"
    new_exe = new / "RobloxPlayerBeta.exe"
    old_exe.write_text("")
    new_exe.write_text("")
    now = time.time()
    os.utime(old_exe, (now - 10, now - 10))
    os.utime(new_exe, (now, now))
    monkeypatch.delenv("DROIDFLEET_ROBLOX", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "missing"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "missing-x86"))
    assert process._process_command("DROIDFLEET_ROBLOX") == str(new_exe)
