@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=python"
set "APP_URL=http://localhost:8501/"

pushd "%PROJECT_DIR%"
start "psy-legis-monitor" /min "%PYTHON_EXE%" -m streamlit run app/ui/streamlit_app.py --global.developmentMode=false --server.address=127.0.0.1 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false

ping 127.0.0.1 -n 7 >nul
start "" "%APP_URL%"

popd
endlocal
