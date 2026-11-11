@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw chimiPack.pyw & exit /b)
where python >nul 2>nul && (start "" python chimiPack.pyw & exit /b)
echo chimiPack needs Python 3.9 or newer: https://www.python.org/downloads/ (tick "Add to PATH").
pause
