@echo off
setlocal
cd /d "%~dp0.."
"C:\Python314\python.exe" -X utf8 -B tools\run_site_crash_test.py --full-tree %*
set "NOS_DENIERS_RESULT=%ERRORLEVEL%"
echo.
echo Rapport : %CD%\reports\crash-test-site-20260924\rapport.html
exit /b %NOS_DENIERS_RESULT%
