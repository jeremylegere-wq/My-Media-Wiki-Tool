@echo off
cd /d "%~dp0"
echo Building a single-file program. This needs internet access for pip.
py -m pip install --user pyinstaller extract-msg
py -m PyInstaller --onefile --name wiki_style_tool --add-data "static;static" --hidden-import wiki_lint --hidden-import house_style --hidden-import rich --hidden-import exporter --hidden-import importer --hidden-import layout --hidden-import templates --hidden-import doc_import wiki_style_tool.py
echo.
echo Done. The program is dist\wiki_style_tool.exe
pause
