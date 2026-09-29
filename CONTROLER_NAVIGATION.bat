@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
echo Controle intensif local : ne ferme pas cette fenetre avant la fin.
echo Parcours complet des commandes et des documents : ce controle peut durer longtemps.
echo Aucun appel a une IA. Resultats enregistres apres chaque scenario.
"%PYTHON_EXE%" -u -X utf8 tools\check_site_navigation.py --serve --intensive --full-controls --check-documents
set "CHECK_EXIT=%ERRORLEVEL%"
powershell -NoProfile -Command "$r=Get-ChildItem -LiteralPath 'reports/navigation-selenium' -Directory | Sort-Object Name | Select-Object -Last 1; if($r){Start-Process -FilePath (Join-Path $r.FullName 'rapport.html')}"
echo Code retour du controle : %CHECK_EXIT%
pause
exit /b %CHECK_EXIT%
