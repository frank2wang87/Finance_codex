@echo off
cd /d "%~dp0"
echo ========================================
echo   正在添加 Windows Defender 防火墙规则
echo ========================================
echo.

echo [1/2] 添加 Python 出站规则...
netsh advfirewall firewall add rule name="Python Stock Data" dir=out program="D:\Program Files\python\python.exe" action=allow
if %errorlevel%==0 (echo   ✓ Python 规则已添加) else (echo   ✗ 添加失败，错误码: %errorlevel%)
echo.

echo [2/2] 添加 Streamlit 出站规则...
netsh advfirewall firewall add rule name="Streamlit Stock Data" dir=out program="D:\Program Files\python\Scripts\streamlit.exe" action=allow
if %errorlevel%==0 (echo   ✓ Streamlit 规则已添加) else (echo   ✗ 添加失败，错误码: %errorlevel%)
echo.

echo ========================================
echo   操作完成！请关闭此窗口后重新运行选股工具
echo ========================================
pause
