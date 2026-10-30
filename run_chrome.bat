@echo off
cd /d "%~dp0"
echo ========================================
echo  A股选股工具 - 最后一步操作
echo ========================================
echo.
echo [步骤1] 正在打开数据页面...
start chrome.exe "https://82.push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21"
echo.
echo [步骤2] 请在Chrome新标签页中按 Ctrl+S 保存文件
echo   保存位置: 当前文件夹 (D:\wangtao\codex\project\Finance)
echo   文件名: stock_data.json
echo   保存类型: JSON文件 (或"所有文件")
echo.
echo [步骤3] 按任意键继续启动分析工具...
pause >nul
echo.
streamlit run app.py
pause
