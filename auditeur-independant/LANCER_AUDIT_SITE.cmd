@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "AUDIT_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%AUDIT_PYTHON%" set "AUDIT_PYTHON=python"
echo Audit independant Nos Deniers - lecture seule, aucun appel IA.
echo Les resultats sont sauvegardes apres chaque scenario.
"%AUDIT_PYTHON%" -X utf8 "%~dp0audit.py" --open %*
set "AUDIT_RESULT=%ERRORLEVEL%"
echo.
if "%AUDIT_RESULT%"=="0" (echo Controles termines. Lire le perimetre du rapport.) else (echo Lire le rapport : anomalie ou verification incomplete.)
pause
exit /b %AUDIT_RESULT%
