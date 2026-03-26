@echo off
chcp 65001 >nul
title PressiomètreIA v2
cd /d "%~dp0"
echo.
echo  ██████╗ ██████╗ ███████╗███████╗███████╗██╗ ██████╗
echo  ██╔══██╗██╔══██╗██╔════╝██╔════╝██╔════╝██║██╔═══██╗
echo  ██████╔╝██████╔╝█████╗  ███████╗███████╗██║██║   ██║
echo  ██╔═══╝ ██╔══██╗██╔══╝  ╚════██║╚════██║██║██║   ██║
echo  ██║     ██║  ██║███████╗███████║███████║██║╚██████╔╝
echo  ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝ ╚═════╝
echo.
echo  PressiometreIA v2 — FastAPI + PyQt6 + KIBALI NF4 4-bit
echo  NF P 94-110 — Pressiometre Menard
echo ────────────────────────────────────────────────────────────
echo.
.\environment\python.exe launcher.py
pause
