@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0.."

set "BOT_NAME=redcomercio_cps"
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
set "LOG_DIR=%CD%\logs"
set "LOG_FILE=%LOG_DIR%\scheduler_%BOT_NAME%.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if not exist "%CD%\.env" (
    echo [%date% %time%] ERROR: No se encontro .env en %CD% >> "%LOG_FILE%"
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [%date% %time%] ERROR: No se encontro Python en %PYTHON_EXE% >> "%LOG_FILE%"
    exit /b 1
)

set /a ATTEMPT=1
set /a MAX_ATTEMPTS=2

:RUN_BOT
echo ============================================================================ >> "%LOG_FILE%"
echo [%date% %time%] Iniciando %BOT_NAME% - Intento %ATTEMPT% de %MAX_ATTEMPTS% >> "%LOG_FILE%"
echo ============================================================================ >> "%LOG_FILE%"

"%PYTHON_EXE%" main.py run -b %BOT_NAME% -p headless=true >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" (
    echo [%date% %time%] FINALIZADO OK: %BOT_NAME% >> "%LOG_FILE%"
    exit /b 0
)

echo [%date% %time%] FALLO %BOT_NAME% con codigo %EXIT_CODE% >> "%LOG_FILE%"

if %ATTEMPT% LSS %MAX_ATTEMPTS% (
    set /a ATTEMPT+=1
    echo [%date% %time%] Reintentando en 60 segundos... >> "%LOG_FILE%"
    timeout /t 60 /nobreak > nul
    goto RUN_BOT
)

echo [%date% %time%] ERROR DEFINITIVO tras %MAX_ATTEMPTS% intentos: %BOT_NAME% >> "%LOG_FILE%"
exit /b %EXIT_CODE%