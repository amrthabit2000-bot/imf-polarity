@echo off
rem Double-click this file to open the IMF polarity window.
cd /d "%~dp0"
python -m imf_polarity.gui
if errorlevel 1 pause
