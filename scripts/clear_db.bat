@echo off
title 清除 lest 数据库
echo ============================================
echo   清除财税助手本地数据库
echo ============================================
echo.
echo 将删除: F:\lest\backend\data\chat.db
echo 删除后所有对话历史与用户画像将清空。
echo.
echo 警告：请先关闭后端窗口（Finance-Backend），
echo       否则文件被占用无法删除！
echo.
pause
echo.
echo 检查后端是否仍在运行（端口 8000）...
netstat -ano | findstr ":8000" | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo.
    echo [WARN] 检测到后端仍在运行（端口 8000）。
    echo        请先关闭 Finance-Backend 窗口，再重新运行本脚本。
    echo.
    pause
    exit /b 1
)
echo 后端未运行，开始删除...
del /q "F:\lest\backend\data\chat.db"
if exist "F:\lest\backend\data\chat.db" (
    echo.
    echo [FAIL] 删除失败：文件仍被占用。请关闭所有相关窗口后重试。
) else (
    echo.
    echo [ OK ] 数据库已删除！
    echo        重启 start.bat 后后端会自动重建空数据库。
)
echo.
pause
