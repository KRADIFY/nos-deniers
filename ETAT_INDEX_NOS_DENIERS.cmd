@echo off
chcp 65001 >nul
cd /d "C:\Users\Jean-Christophe\Documents\ChatGPT\docker\budget"
"C:\Users\Jean-Christophe\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "tools\retrieval_campaign.py" status
pause
