@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py wiki_style_tool.py) || (python wiki_style_tool.py)
pause
