# MLab Webリーダーの設定

Webリーダーは、端末に保存した読書用HTMLから訳文・原文・図表を表示します。HTMLに埋め込まれたPDFダウンロードリンクは、元のHTMLをブラウザで直接開くと使えます。

## 外出先で読む

1. Google Driveなどの公式アプリで、`MLab Web Library` の読書用HTMLを端末に保存します。
2. [MLab Webリーダー](https://mlabpages.github.io/plamo-babeldoc/)で「端末のファイルを開く」を押し、そのHTMLを選びます。

Googleへのログインは公式アプリや公式サイト上で行います。Webリーダーは端末から選んだファイルをブラウザ内で読み取ります。

## GitHub Pages

1. Settings → Pages で公開元に GitHub Actions を選びます。
2. Actions の「Deploy Web Reader」を実行し、表示されたPages URLを開きます。

公開されるのはリーダーのHTML・CSS・JavaScriptとプライバシーページです。

## ローカル確認

`python -m http.server 8000 --bind 127.0.0.1 --directory web` を実行し、ブラウザで `http://localhost:8000` を開きます。
