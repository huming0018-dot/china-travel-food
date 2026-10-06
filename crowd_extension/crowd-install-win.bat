@echo off
rem 众包美食家 · Windows 一键安装（双击运行，无需 Python/任何开发环境）
rem
rem 原理：写入 Chrome 企业策略 ExtensionInstallForcelist —— Chrome 自己从项目更新服务器
rem 下载、安装插件，以后每次发布新版本自动升级，无需再装。
rem 需要：管理员权限一次（脚本会自动弹 UAC 请求）；本机装有 Chrome。
chcp 65001 >nul
setlocal
set EXT_ID=licijehcpohikchlnkbpjdjdfkcocndg
set UPDATE_URL=https://huming0018-dot.github.io/crowd-pages/updates.xml
set ENTRY=%EXT_ID%;%UPDATE_URL%

title 众包美食家 · 一键安装（Windows）
echo ===============================================
echo   众包美食家 · 一键安装（Windows）
echo ===============================================
echo.
echo 这一步会把插件登记进 Chrome 的企业策略，之后 Chrome
echo 自动完成安装，以后每次升级都会自动更新，无需重装。
echo.

rem 1. 自检管理员权限，没有则通过 UAC 自提权重启自己
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 需要管理员权限，正在请求 UAC 授权...
  powershell -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)

rem 2. 检测 Chrome
set CHROME_EXE=
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHROME_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHROME_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set CHROME_EXE=%LocalAppData%\Google\Chrome\Application\chrome.exe
if not defined CHROME_EXE (
  echo ❌ 未检测到 Chrome，请先安装 Chrome 浏览器后再运行本脚本。
  pause
  exit /b 1
)

rem 3. 写入策略（已存在则覆盖为同一值，幂等）
reg add "HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist" /v "1001" /t REG_SZ /d "%ENTRY%" /f >nul
if %errorlevel% equ 0 (
  echo ✅ 已登记到 Chrome 策略。
) else (
  echo ❌ 写入策略失败，请右键本脚本 → 以管理员身份运行。
  pause
  exit /b 1
)

rem 4. 重启 Chrome 让策略生效
echo.
echo 即将重启 Chrome 让插件自动安装（请先保存浏览器里未提交的页面）。
pause
taskkill /im chrome.exe /f >nul 2>&1
timeout /t 2 >nul
start "" "%CHROME_EXE%"

echo.
echo ===============================================
echo   完成！接下来：
echo   1. Chrome 重启后会自动装好「众包美食家」插件
echo      （约 1 分钟内；插件图标出现在右上角拼图里）
echo   2. 首次安装会自动打开「参与协议」页：
echo      点【我要加入】自动获得参与编号 → 点【同意并开始使用】
echo   3. 如果之前手动装过旧版本（开发者模式装的），
echo      请到 chrome://extensions 把旧的移除，避免重复
echo.
echo   以后插件升级全自动，不需要再运行本脚本。
echo ===============================================
pause
