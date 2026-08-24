@echo off
cd /d "%~dp0"
python character_suite.py
if errorlevel 1 pause
