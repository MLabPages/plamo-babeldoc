# PLaMo 論文リーダー

論文PDFを、元のレイアウトを保ったまま日本語に訳して読むWindowsアプリです。
レイアウト処理は [BabelDOC](https://github.com/funstory-ai/BabelDOC)、翻訳はPC内で動く
Preferred Networks の **PLaMo 3 Translate**（0.8B / 2B / 8B）か、Google の **Gemini** を選べます。

## 起動

デスクトップかスタートメニューの「PLaMo論文リーダー」を開きます。

- ショートカットを作り直すとき: `powershell -ExecutionPolicy Bypass -File tools\make_shortcuts.ps1`
- ブラウザで開くとき: `.venv\Scripts\python.exe app.py --browser`

## できること

- **翻訳**: PDFをドロップするかボタンで選ぶと翻訳が始まります。同じ論文を別のエンジンでも訳して見比べられます。
- **読書モード**: 本文を1段で読みやすく流し直します。図は画像で、数式は元ページの切り抜きで表示します。
  - 背景（白・セピア・黒）、書体（明朝・ゴシック）、文字の大きさ・行間・幅を変えられます
  - 段落をタップすると原文が出ます。「原文を併記する」で全段落に原文を並べます
  - **集中モード**（ボタンか F キー）: 上のバーを隠し、いま読んでいる段落以外を薄くします
  - 読んだ位置は自動で覚えます
- **読み上げ**: 日本語の声で段落ごとに読み上げ、読んでいる段落を強調します。速さと声を選べます
  （Windows では Haruka / Ayumi / Nanami など、iPad では Kyoko など、端末に入っている声を使います）。
- **PDF / 対訳**: 翻訳済みPDFと、原文と訳文を並べたPDFをそのまま開けます。
- **iPadで読む**: 「iPadで読む」→「共有を開始」でQRコードが出ます。同じWi‑FiのiPadで読み取ると、
  Safariでライブラリ・読書モード・読み上げが使えます。共有ボタンで止めるか、アプリを閉じると止まります。

## 翻訳エンジン

| エンジン | 置き場所 | 6ページの論文の目安 | 特徴 |
| --- | --- | --- | --- |
| PLaMo 0.8B | PC内 | 約1.5分 | 最速。ときどき語の崩れや誤訳がある |
| PLaMo 2B | PC内 | 約1.5分 | 標準。読みやすさと速さの釣り合いがよい |
| PLaMo 8B | PC内 | 約5.5分 | いちばん自然。時間がかかる |
| Gemini | Google | — | 設定でAPIキーを登録すると使える。本文がGoogleへ送られる |

PLaMo は内蔵GPU（Intel Arc, Vulkan）で `llama/llama-server.exe` を動かします。モデルを切り替えると、
サーバーは自動で入れ替わります。Gemini のキーとモデル名は `%APPDATA%\PLaMoPaperReader\settings.json` に保存されます。

## 用語集

`glossary.csv` に `source,target` の形で訳語を書くと、その語を含む段落にだけ用語指定を付けて訳します（Gemini にも渡します）。

## コマンドで使う

```powershell
.\.venv\Scripts\python.exe run_plamo.py 論文.pdf --engine plamo-8b --pages 1-3
```

PDF を `translate.bat` にドラッグ＆ドロップしても訳せます（2B、結果は `output` フォルダ）。

## 構成

- `app.py`: アプリの入口（pywebview の窓）。二重起動するとすでに開いているアプリを使います
- `paperapp/server.py`: 画面・iPad共有用のHTTPサーバー、ライブラリ（`library/`）、翻訳ジョブの順番待ち
- `paperapp/worker.py`: BabelDOC を別プロセスで動かし、進み具合を返す。1件も訳せなかったときは失敗として扱う
- `paperapp/translators.py`: PLaMo 用（目標言語・常体・用語集、出力の上限と繰り返しの抑制）と Gemini 用の翻訳部品
- `paperapp/engines.py`: エンジンの一覧と llama-server の起動・切り替え
- `paperapp/reading.py`: 翻訳済みPDFから読書モード用の段落・見出し・図・数式を取り出す
- `paperapp/static/`: 画面（HTML / CSS / JavaScript）

PLaMo 3 Translate は PLaMo Community License の範囲で、年間売上10億円以下の個人・企業なら無料で使えます。
