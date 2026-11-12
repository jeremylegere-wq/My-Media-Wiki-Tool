@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py wiki_style_tool.py --make-shortcut) || (python wiki_style_tool.py --make-shortcut)
pause
