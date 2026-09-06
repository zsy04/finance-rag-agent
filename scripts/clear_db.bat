@echo off
title Clear lest local database
echo ============================================
echo   Clear Finance Assistant local database
echo ============================================
echo.
echo Will delete: %~dp0..\backend\data\chat.db
echo All chat history and user profiles will be cleared.
echo.
echo WARNING: close the backend window (Finance-Backend) first,
echo          otherwise the file is locked and cannot be deleted!
echo.
pause
echo.
echo Checking whether the backend is still running (port 8000)...
netstat -ano | findstr ":8000" | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo.
    echo [WARN] Backend still running on port 8000.
    echo        Close the Finance-Backend window first, then rerun.
    echo.
    pause
    exit /b 1
)
echo Backend not running, deleting database...
del /q "%~dp0..\backend\data\chat.db"
if exist "%~dp0..\backend\data\chat.db" (
    echo.
    echo [FAIL] Delete failed: file still locked. Close all windows and retry.
) else (
    echo.
    echo [ OK ] Database deleted!
    echo        Restart start.bat to recreate an empty database.
)
echo.
pause