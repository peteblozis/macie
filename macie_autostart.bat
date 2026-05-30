@echo off
REM MACIE Auto-Start Script
REM Runs automatically when Windows starts
REM Starts both the web server and Cloudflare tunnel

cd /d C:\SageForge\macie

REM Start the Cloudflare tunnel in background
start "MACIE Tunnel" /min cloudflared tunnel run macie

REM Wait 3 seconds for tunnel to establish
timeout /t 3 /nobreak > nul

REM Start the MACIE web server in background
start "MACIE Web Server" /min python macie_web.py

echo MACIE is running at http://localhost:5000/macie
