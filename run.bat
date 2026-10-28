@echo off
title LinkForge Autonomous SEO Command Center
echo ========================================================
echo   LinkForge Autonomous SEO Guest Post ^& Backlink Dashboard
echo   Starting server on http://localhost:8000
echo ========================================================
echo.
cd /d "%~dp0"
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause
