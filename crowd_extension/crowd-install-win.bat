@echo off
chcp 65001 >nul 2>&1
rem ============================================================
rem  美食图鉴·众包采集插件 — Windows 一键安装器
rem  无需 Python / 无任何开发环境。双击即可。
rem  自动完成：解压插件 → 打开扩展页 → 复制插件路径到剪贴板
rem ============================================================
setlocal enabledelayedexpansion

echo ==============================================
echo   美食图鉴 · 众包采集插件 一键安装 (Windows)
echo ==============================================
echo.

rem 0) 脚本所在目录
set "SCRIPT_DIR=%~dp0"
set "WORK_DIR=%USERPROFILE%\.food-crowd"
set "EXT_DIR=%WORK_DIR%\crowd-extension-v3.2.0"

rem 1) 找 zip
set "ZIP_SRC="
if exist "%SCRIPT_DIR%crowd-extension-v3.2.0.zip" set "ZIP_SRC=%SCRIPT_DIR%crowd-extension-v3.2.0.zip"
if not defined ZIP_SRC if exist "%USERPROFILE%\Downloads\crowd-extension-v3.2.0.zip" set "ZIP_SRC=%USERPROFILE%\Downloads\crowd-extension-v3.2.0.zip"

if not defined ZIP_SRC (
  echo [X] 没找到 crowd-extension-v3.2.0.zip
  echo     请先回到报名/安装页下载插件 zip（与安装器放同一文件夹即可）。
  echo.
  pause
  exit /b 1
)
echo [OK] 找到插件包: %ZIP_SRC%

rem 2) 解压到固定目录（用系统自带 tar，Windows 10 1803+ 均有）
rem    修复（外部审计 #57）：zip 根目录即插件本体（无外层文件夹），必须解压到 EXT_DIR，
rem    与 mac 安装器保持一致，避免加载路径指向不存在的目录。
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
if exist "%EXT_DIR%" rmdir /s /q "%EXT_DIR%"
mkdir "%EXT_DIR%"
echo [OK] 解压中…
tar -xf "%ZIP_SRC%" -C "%EXT_DIR%"
if errorlevel 1 (
  echo [X] 解压失败，请确认 zip 文件完整后重试。
  pause
  exit /b 1
)
echo [OK] 插件已解压到: %EXT_DIR%

rem 3) 自动探测 Chrome 系浏览器
set "BROWSER_EXE="
for %%A in (
  "chrome" "msedge" "brave" "chromium"
) do (
  where %%A >nul 2>&1
  if not errorlevel 1 set "BROWSER_EXE=%%~A"
)

if not defined BROWSER_EXE (
  rem 回退：常见安装路径
  if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  if not defined BROWSER_EXE if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
)

if not defined BROWSER_EXE (
  echo [X] 未检测到 Chrome / Edge / Brave。请先安装任一 Chrome 系浏览器后重试。
  pause
  exit /b 1
)
echo [OK] 检测到浏览器: %BROWSER_EXE%

rem 4) 复制插件路径到剪贴板（powershell 单行）
echo %EXT_DIR%| powershell -command "$x=$input; Set-Clipboard -Value $x" >nul 2>&1
echo [OK] 插件文件夹路径已复制到剪贴板

rem 5) 打开扩展管理页
if /i "%BROWSER_EXE%"=="msedge" (
  start "" "%BROWSER_EXE%" edge://extensions
) else (
  start "" "%BROWSER_EXE%" chrome://extensions
)
echo [OK] 已打开扩展管理页

echo.
echo ==============================================
echo   最后一步（30 秒完成）：
echo   1. 在扩展页右上角 开启「开发者模式」
echo   2. 点「加载已解压的扩展程序」
echo   3. 在弹窗里按 Ctrl+V 粘贴路径 → 回车
echo ==============================================
echo.
echo 安装完成后：点浏览器右上角 拼图图标 → 插件「选项」→
echo 填写参与编号（P-XXXXXX）并同意协议 → 回到小红书页面启动采集。
echo.
pause
