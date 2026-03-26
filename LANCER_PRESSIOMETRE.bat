@echo off
chcp 65001 > nul
title Pressiometre IA - KIBALI

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║           PRESSIOMETRE IA  -  KIBALI GEOPHYSIQUE        ║
echo  ║         Analyse pressiometrique intelligente NF P94-110  ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.
echo  Demarrage de l'application...
echo  (La fenetre du navigateur va s'ouvrir automatiquement)
echo.

:: Dossier du script
set SCRIPT_DIR=%~dp0

:: Python portable
set PYTHON=%SCRIPT_DIR%environment\python.exe

:: Verifier Python
if not exist "%PYTHON%" (
    echo  [ERREUR] Python portable introuvable : %PYTHON%
    pause
    exit /b 1
)

:: Lancer Streamlit
"%PYTHON%" -m streamlit run "%SCRIPT_DIR%app.py" ^
    --server.port=8501 ^
    --server.headless=false ^
    --browser.gatherUsageStats=false ^
    --theme.base=dark ^
    --theme.primaryColor=#00b4d8 ^
    --theme.backgroundColor=#0e1117 ^
    --theme.secondaryBackgroundColor=#1e2a3a ^
    --theme.textColor=#ffffff

pause
