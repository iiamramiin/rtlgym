@echo off
rem Double-click: installs WSL/Ubuntu if needed, sets up rtlgym, runs the local-model experiment.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_all.ps1"
