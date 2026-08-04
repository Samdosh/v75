@echo off
cd /d "%~dp0"
title Deriv Trading Bot
:restart
echo ========================================
echo  🔥 Deriv Trading Bot Starting...
echo ========================================
python main.py
echo.
echo ⏹ Bot stopped. Restarting in 10 seconds...
timeout /t 10
goto restart
