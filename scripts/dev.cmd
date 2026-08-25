@echo off
REM Start the API and the frontend dev server in their own windows.
REM
REM Double-click this rather than having an agent or terminal session launch
REM them: anything spawned from a tool session gets killed when that session
REM tears down, which is why the servers kept disappearing between turns.
REM Close the two windows to stop them.

set ROOT=%~dp0..

start "PIB Direct API" cmd /k "cd /d "%ROOT%" && .venv\Scripts\pib-agent.exe serve"
start "PIB Direct web" cmd /k "cd /d "%ROOT%\frontend" && npm run dev"

timeout /t 12 /nobreak >nul
start "" http://localhost:5173/
