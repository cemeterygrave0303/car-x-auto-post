@echo off
chcp 65001 >nul
echo ============================================
echo  中古車在庫管理システム 起動中...
echo ============================================
echo.

:: 仮想環境の確認
if not exist ".venv\Scripts\streamlit.exe" (
    echo [エラー] セットアップが完了していません。
    echo  先に install.bat を実行してください。
    pause
    exit /b 1
)

:: .env の確認
if not exist ".env" (
    echo [エラー] .env ファイルが見つかりません。
    echo  install.bat を実行してください。
    pause
    exit /b 1
)

:: service_account.json の確認
if not exist "service_account.json" (
    echo [警告] service_account.json が見つかりません。
    echo  Google Sheets への接続に失敗する可能性があります。
    echo.
)

echo  ブラウザが自動で開きます...
echo  アドレス: http://localhost:8501
echo.
echo  終了するにはこのウィンドウを閉じてください。
echo ============================================
echo.

:: Streamlit 起動（ブラウザを自動で開く）
call .venv\Scripts\streamlit.exe run app.py ^
    --server.headless false ^
    --browser.gatherUsageStats false ^
    --server.port 8501

pause
