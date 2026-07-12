@echo off
setlocal

powershell.exe -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -like '*streamlit*app/ui/streamlit_app.py*' -or $_.CommandLine -like '*streamlit*app\ui\streamlit_app.py*' -or $_.CommandLine -like '*run_streamlit.py*') }; foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force }; Write-Host ('Processi dashboard fermati: ' + @($procs).Count)"

pause
endlocal
