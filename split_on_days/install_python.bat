@echo off
echo Downloading Python 3.12.5...
curl -o python-3.12.5-amd64.exe https://www.python.org/ftp/python/3.12.5/python-3.12.5-amd64.exe
echo.
echo Installing Python 3.12.5...
python-3.12.5-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
echo.
echo Cleaning up installer...
del python-3.12.5-amd64.exe
echo.
echo Python 3.12.5 installed successfully.
pause
