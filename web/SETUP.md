# MLab Webリーダーの設定

Webリーダーは、MLab論文リーダーで書き出した既存のHTMLから訳文・原文・図表を表示します。HTMLに埋め込まれたPDFダウンロードリンクは、元のHTMLを直接開くと使えます。

## Google Cloud

1. 自分が管理するGoogle Cloudプロジェクトで Google Drive API と Google Picker API を有効にします。
2. Google Auth Platformでアプリ名、連絡先、対象ユーザー、`https://www.googleapis.com/auth/drive.file` を設定します。個人のGoogleアカウントでテストする場合は外部・テストを選び、利用するアカウントをテストユーザーに追加します。組織のアカウントは管理者の接続制限が適用されます。
3. 「ウェブ アプリケーション」のOAuthクライアントを作成し、配信サイトのオリジンを「承認済みのJavaScript生成元」に登録します。GitHub Pagesなら、例として `https://mlabpages.github.io` を登録します。ローカルの接続テストでは `http://localhost:8000` を登録します。
4. Picker用APIキーを作り、HTTPリファラーを配信サイトに絞ります。APIの制限は Google Picker API と Google Drive API を指定します。同じプロジェクトのOAuthクライアントID、APIキー、数字のプロジェクト番号を使います。
5. 一般向けに提供する場合は、配信サイトのホームと `privacy.html` のURLをGoogle Auth Platformで設定し、Googleの画面で求められる公開・審査手続きに従います。

[Google Pickerの設定](https://developers.google.com/workspace/drive/picker/guides/web-picker) · [Driveのアクセス範囲](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) · [Google OAuth 2.0ポリシー](https://developers.google.com/identity/protocols/oauth2/policies)

## GitHub Pages

1. リポジトリの Settings → Pages で公開元に GitHub Actions を選びます。
2. Settings → Secrets and variables → Actions → Variables に `MLAB_GOOGLE_CLIENT_ID`、`MLAB_GOOGLE_API_KEY`、`MLAB_GOOGLE_PROJECT_NUMBER` を登録します。ブラウザへ配信される識別情報なので、OAuthクライアントシークレットは使用しません。
3. Actions の「Deploy Web Reader」を実行し、表示されたPages URLを開きます。

公開されるのはリーダーのHTML・CSS・JavaScriptとプライバシーページです。デスクトップアプリのライブラリや論文ファイルは配信物に含まれません。

## ローカル確認

`python -m http.server 8000 --bind 127.0.0.1 --directory web` を実行し、ブラウザで `http://localhost:8000` を開きます。Drive連携も試す場合は、ローカル作業用コピーの `config.js` に `clientId`、`apiKey`、`projectNumber` を設定します。
