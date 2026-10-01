@echo off
echo Installing Python packages...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo Error: failed to install packages.
)
pause
