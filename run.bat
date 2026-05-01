@echo off
:: Double-click launcher for VideoCaptioner.
:: Delegates to scripts/run.bat which auto-installs uv / ffmpeg, syncs deps,
:: then launches the GUI via `uv run videocaptioner`.
cd /d "%~dp0"
call "%~dp0scripts\run.bat" %*
