# PLaMo × BabelDOC ローカル論文翻訳

BabelDOC（レイアウトを保った PDF 翻訳）の翻訳部分を、PC 上で動く Preferred Networks の
翻訳専用モデル PLaMo 3 Translate（2B, Q4_K_M）に差し替えたものです。論文の中身は外部へ送られず、
回数の上限もありません。

## 使い方

翻訳したい PDF を `translate.bat` にドラッグ＆ドロップします。翻訳サーバーが止まっていれば自動で起動し、
結果は `output` フォルダに次の 2 種類で出ます。

- `*.ja.mono.pdf`：日本語だけの版
- `*.ja.dual.pdf`：原文ページと訳文ページを並べた版

コマンドで使う場合:

```powershell
.\start_server.ps1
.\.venv\Scripts\python.exe run_plamo.py 論文.pdf --pages 1-3
```

BabelDOC のオプション（`--pages`、`--no-dual` など）はそのまま後ろに付けられます。

## 用語集

`glossary.csv` に `source,target` の形で訳語を書くと、その語を含む段落にだけ用語指定を付けて翻訳します。

## 構成

- `run_plamo.py`：BabelDOC を呼び出し、翻訳だけ PLaMo の入力形式（目標言語・常体・用語集）で 1 段落ずつ送る
- `start_server.ps1`：`llama/llama-server.exe`（llama.cpp b12211, Vulkan）を 127.0.0.1:8090 で起動
- `models/`：`pfnet/plamo-3-translate-2b-GGUF` の Q4_K_M
- BabelDOC 0.7.1 は `.venv`、キャッシュやレイアウト解析モデルは `home/.cache/babeldoc` に置く

Ollama 0.33.3 は PLaMo 3 のトークナイザーに未対応のため、llama.cpp を直接使っています。
PLaMo 3 Translate は年間売上 10 億円以下の個人・企業なら PLaMo Community License の範囲で無料利用できます。
