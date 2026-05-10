@echo off
chcp 65001 >nul
echo ============================================
echo  中古車在庫管理システム セットアップ
echo ============================================
echo.

:: Python の確認
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python が見つかりません。インストールします...
    echo.
    winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [エラー] Python のインストールに失敗しました。
        echo   手動で https://www.python.org/downloads/ からインストールしてください。
        pause
        exit /b 1
    )
    echo [完了] Python をインストールしました。
    echo.
    :: PATH を再読み込みするため新しいコマンドプロンプトで続行
    echo 新しいウィンドウでセットアップを続行します...
    start cmd /k "%~f0"
    exit
)

echo [OK] Python が見つかりました。
python --version
echo.

:: 仮想環境の作成
if not exist ".venv" (
    echo [1/3] 仮想環境を作成しています...
    python -m venv .venv
    echo [完了] 仮想環境を作成しました。
) else (
    echo [OK] 仮想環境はすでに存在します。
)
echo.

:: パッケージのインストール
echo [2/3] 必要なパッケージをインストールしています...
echo       （初回は数分かかります）
call .venv\Scripts\pip.exe install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [エラー] パッケージのインストールに失敗しました。
    pause
    exit /b 1
)
echo [完了] パッケージをインストールしました。
echo.

:: .env ファイルの確認
echo [3/3] 設定ファイルを確認しています...
if not exist ".env" (
    copy .env.example .env >nul
    echo [!] .env ファイルを作成しました。
    echo     .env をメモ帳で開いて各APIキーを設定してください。
    echo.
    start notepad .env
) else (
    echo [OK] .env ファイルが見つかりました。
)

:: service_account.json の確認
if not exist "service_account.json" (
    echo.
    echo [!] service_account.json が見つかりません。
    echo     Google Cloud Console からダウンロードして
    echo     このフォルダに置いてください。
)

echo.
echo ============================================
echo  セットアップ完了！
echo  start.bat をダブルクリックしてアプリを起動してください。
echo ============================================
echo.
pause
