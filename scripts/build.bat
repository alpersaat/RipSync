@echo off
title RipSync - Build Standalone EXE and Installer
echo ========================================================
echo RipSync - Standalone EXE ve Kurulum Paketi Olusturucu
echo ========================================================
cd /d "%~dp0\.."
python build_exe.py
pause

