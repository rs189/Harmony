@echo off
cd /d "%~dp0python"

echo Starting Harmony Host Listener
echo ---

elevate -c python.exe ..\listener.py