@echo off
REM Instalare din sursa: mediul Python (.venv) si interfata (ui\node_modules).
REM Cere Python 3.11+ si Node.js deja instalate.
cd /d "%~dp0"
where python >nul 2>nul || (echo Lipseste Python: winget install Python.Python.3.12 & pause & exit /b 1)
where npm >nul 2>nul || (echo Lipseste Node.js: winget install OpenJS.NodeJS.LTS & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" python -m venv .venv || goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto fail
pushd ui
call npm install --no-audit --no-fund || (popd & goto fail)
popd
".venv\Scripts\python.exe" app.py --selfcheck
echo.
echo Gata. Porneste cu START.bat
pause
exit /b 0

:fail
echo Instalarea a esuat, vezi mesajele de mai sus.
pause
exit /b 1
