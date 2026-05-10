# 中古車 X 自動投稿システム

Googleスプレッドシートに登録された中古車在庫を読み込み、X（旧Twitter）へ自動投稿するPythonアプリケーションです。

---

## 1. 概要

- Googleスプレッドシートの在庫一覧から「販売中」かつ「未投稿」の車両を1件選んでXへ投稿する
- 投稿成功後にスプレッドシートへ結果（投稿済みフラグ・日時・投稿ID）を書き戻す
- GitHub Actions で毎日 8:30 / 20:30 JST に自動実行できる
- `DRY_RUN=true` で投稿せずに投稿予定文だけ確認できる

---

## 2. 必要なAPI

| API | 用途 | 取得先 |
|-----|------|--------|
| Google Sheets API | スプレッドシートの読み書き | Google Cloud Console |
| X API v2 (Free/Basic) | ツイートの投稿 | X Developer Portal |

---

## 3. Google Sheets API 設定方法

### 3-1. Google Cloud Console でプロジェクトを作成

1. [Google Cloud Console](https://console.cloud.google.com/) を開く
2. 画面上部の「プロジェクトを選択」→「新しいプロジェクト」をクリック
3. プロジェクト名を入力して「作成」

### 3-2. Google Sheets API を有効化

1. 左メニュー「APIとサービス」→「ライブラリ」
2. 「Google Sheets API」を検索してクリック
3. 「有効にする」をクリック

---

## 4. サービスアカウント作成方法

1. Google Cloud Console の左メニュー「IAMと管理」→「サービスアカウント」
2. 「サービスアカウントを作成」をクリック
3. 名前を入力（例：`car-post-bot`）→「作成して続行」
4. ロールは「編集者」または「Sheets 編集者」を選択 → 「完了」
5. 作成されたサービスアカウントをクリック →「キー」タブ
6. 「キーを追加」→「新しいキーを作成」→「JSON」→「作成」
7. ダウンロードされた JSON ファイルを `service_account.json` としてプロジェクトフォルダに置く

> **重要**: `service_account.json` は `.gitignore` に含まれています。Gitにコミットしないでください。

---

## 5. スプレッドシートをサービスアカウントに共有する手順

1. 対象のスプレッドシートを開く
2. 右上「共有」ボタンをクリック
3. サービスアカウントのメールアドレスを入力（例：`car-post-bot@your-project.iam.gserviceaccount.com`）
4. 権限を「編集者」に設定して「送信」
5. サービスアカウントのメールアドレスは `service_account.json` 内の `client_email` フィールドで確認できる

---

## 6. X Developer Portal で必要な権限

1. [X Developer Portal](https://developer.twitter.com/en/portal/dashboard) にログイン
2. アプリを作成または選択
3. アプリの「Settings」→「User authentication settings」で以下を設定：
   - **App permissions**: `Read and Write`（投稿に必要）
   - **Type of App**: `Web App, Automated App or Bot`
4. 「Keys and Tokens」タブで以下を取得：
   - **API Key** (Consumer Key)
   - **API Key Secret** (Consumer Secret)
   - **Access Token**（`Generate` ボタンで生成）
   - **Access Token Secret**

> **注意**: App permissions を変更した後は必ず Access Token を再生成してください。変更前に発行したトークンは旧権限のままです。

---

## 7. .env の設定方法

```bash
cp .env.example .env
```

`.env` を開いて各項目を設定する：

```env
# サービスアカウントJSONファイルのパス
GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json

# スプレッドシートID（URLの /d/〜/edit の部分）
SPREADSHEET_ID=1Aay3nS-4Ftb5MsYk-Spu1kvRtHUCLh3G

# シート名（タブ名）
SHEET_NAME=在庫一覧

# X API キー（Developer Portal から取得）
X_API_KEY=ここにAPIキーを入力
X_API_SECRET=ここにAPIシークレットを入力
X_ACCESS_TOKEN=ここにアクセストークンを入力
X_ACCESS_TOKEN_SECRET=ここにアクセストークンシークレットを入力

# DRY RUN: true にすると投稿せず確認のみ
DRY_RUN=false
```

---

## 8. ローカル実行方法

### 前提条件
- Python 3.10 以上
- `service_account.json` を配置済み
- `.env` を設定済み

### セットアップ

```bash
cd car-x-auto-post

# 仮想環境を作成（推奨）
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt
```

### 動作確認（DRY RUN）

```bash
# 投稿せずに投稿予定文を確認する
DRY_RUN=true python main.py
```

### 本番実行

```bash
python main.py
```

### X API 認証テスト

```python
from x_client import XClient
x = XClient()
x.verify_credentials()  # @アカウント名が表示されれば成功
```

---

## 9. GitHub Actions での定期実行方法

### 9-1. リポジトリにファイルをプッシュ

```
.github/
  workflows/
    car-post.yml   ← github-actions/car-post.yml をここに移動またはコピー
car-x-auto-post/
  main.py
  ...
```

> `github-actions/car-post.yml` を `.github/workflows/car-post.yml` にコピーしてください。

### 9-2. GitHub Secrets を設定

リポジトリの「Settings」→「Secrets and variables」→「Actions」→「New repository secret」で以下を登録：

| Secret名 | 値 |
|----------|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `service_account.json` の**中身（JSON文字列）**を貼り付け |
| `SPREADSHEET_ID` | スプレッドシートID |
| `SHEET_NAME` | シート名（例: `在庫一覧`）|
| `X_API_KEY` | X API Key |
| `X_API_SECRET` | X API Secret |
| `X_ACCESS_TOKEN` | X Access Token |
| `X_ACCESS_TOKEN_SECRET` | X Access Token Secret |

> `GOOGLE_SERVICE_ACCOUNT_JSON` には JSON ファイルの**中身全体**を文字列として貼り付けてください（ファイルパスではありません）。

### 9-3. 実行スケジュール

| タイミング | JST | UTC (cron) |
|-----------|-----|-----------|
| 朝 | 8:30 JST | `30 23 * * *` |
| 夜 | 20:30 JST | `30 11 * * *` |

### 9-4. 手動実行

GitHub の「Actions」タブ →「中古車 X 自動投稿」→「Run workflow」から手動実行できます。DRY RUN モードも選択可能です。

---

## 10. よくあるエラーと対処法

### `gspread.exceptions.SpreadsheetNotFound`
- スプレッドシートIDが間違っている
- サービスアカウントにスプレッドシートが共有されていない → 手順5を確認

### `gspread.exceptions.WorksheetNotFound`
- `SHEET_NAME` で指定したシート名がスプレッドシートに存在しない
- シートのタブ名を確認して `.env` の `SHEET_NAME` を修正する

### `tweepy.errors.Forbidden: 403 Forbidden`
- X API の App permissions が `Read only` になっている
- Developer Portal で `Read and Write` に変更後、Access Token を**再生成**する

### `tweepy.errors.Unauthorized: 401 Unauthorized`
- API キーまたはトークンが間違っている
- `.env` の各キーに余分なスペースや改行が入っていないか確認する

### `FileNotFoundError: service_account.json`
- `service_account.json` がプロジェクトフォルダに配置されていない
- または `GOOGLE_SERVICE_ACCOUNT_JSON` のパスが間違っている

### 投稿対象が見つからない
- スプレッドシートの「ステータス」列が「販売中」になっているか確認
- 「投稿済み」列が `TRUE` になっていないか確認
- 車種名・価格・年式・走行距離のいずれかが空でないか確認

---

## 11. スプレッドシートに追加すべきカラム

以下のカラムがない場合は追加することを推奨します：

| カラム名 | 説明 | 必須 |
|--------|------|------|
| `投稿済み` | 投稿完了後に `TRUE` が書き込まれる | 推奨 |
| `最終投稿日時` | 投稿日時（`YYYY-MM-DD HH:MM:SS` 形式） | 推奨 |
| `投稿回数` | 累計投稿回数（整数） | 任意 |
| `X投稿ID` | 投稿したツイートのID | 推奨 |
| `優先順位` | 数値が大きいほど先に投稿される | 任意 |

---

## 12. セキュリティ注意事項

- `.env` と `service_account.json` は **`.gitignore` に設定済み**です。絶対にコミットしないでください
- Xのログインパスワードはコードにも設定ファイルにも使用しません。APIキーとアクセストークンのみを使用します
- GitHub Secrets に登録した情報はログに出力されません
- エラーログにAPIキーやトークンが含まれないよう `SecretFilter` を実装しています
- リポジトリを公開する場合は `.env.example` のみをコミットしてください
