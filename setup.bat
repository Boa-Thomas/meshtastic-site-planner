@echo off
REM ============================================================================
REM Meshtastic Site Planner — Setup ^& Startup Script (Windows)
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ===================================================
echo   Meshtastic Site Planner — Setup
echo  ===================================================
echo.

REM ── Check dependencies ─────────────────────────────────────────────────────

where docker >nul 2>&1 || (
    echo [ERROR] docker is required but not installed.
    echo         Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/
    exit /b 1
)

where git >nul 2>&1 || (
    echo [ERROR] git is required but not installed.
    echo         Install Git: https://git-scm.com/download/win
    exit /b 1
)

REM Check docker compose plugin
docker compose version >nul 2>&1
if %errorlevel% equ 0 (
    set "COMPOSE=docker compose"
    echo [INFO]  Using: docker compose
) else (
    where docker-compose >nul 2>&1
    if %errorlevel% equ 0 (
        set "COMPOSE=docker-compose"
        echo [INFO]  Using: docker-compose
    ) else (
        echo [ERROR] docker compose is required but not installed.
        exit /b 1
    )
)

REM ── Git submodules ─────────────────────────────────────────────────────────

if not exist "splat\splat.cpp" (
    echo [INFO]  Initializing git submodules...
    git submodule update --init --recursive
) else (
    echo [INFO]  Git submodules already initialized.
)

REM ── Environment file ───────────────────────────────────────────────────────

if not exist ".env" (
    echo [INFO]  Creating .env from .env.example...
    copy .env.example .env >nul
    echo [WARN]  Review .env and adjust settings for your environment.
) else (
    echo [INFO]  .env already exists — skipping copy.
)

REM ── Build and start ────────────────────────────────────────────────────────

echo.
echo [INFO]  Building and starting all services...
%COMPOSE% up --build -d

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start services. Check Docker Desktop is running.
    exit /b 1
)

echo.
echo  ===================================================
echo   Services started successfully!
echo  ===================================================
echo.
echo   %COMPOSE% ps                  — Check service status
echo   %COMPOSE% logs -f app         — Follow app logs
echo   %COMPOSE% logs -f worker      — Follow light worker logs
echo   %COMPOSE% logs -f autoscaler  — Follow autoscaler logs
echo   %COMPOSE% down                — Stop all services
echo.
echo   Flower dashboard:  http://localhost:5555
echo   Application:       http://localhost:8080
echo.

endlocal
