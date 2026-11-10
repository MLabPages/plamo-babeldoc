# PLaMo 論文リーダー

論文PDFを、元のレイアウトを保ったまま日本語に訳して読むWindowsアプリです。
レイアウト処理は [BabelDOC](https://github.com/funstory-ai/BabelDOC)、翻訳はPC内で動く
Preferred Networks の **PLaMo 3 Translate**（0.8B / 2B / 8B）か、Google の **Gemini** を選べます。

## 導入（Windows 10 / 11）

### インストーラーで入れる（おすすめ）

1. [リリースページ](https://github.com/MLabPages/plamo-babeldoc/releases/latest) から
   `PLaMoPaperReader-Setup.exe` をダウンロードして、ダブルクリックします。
2. 「WindowsによってPCが保護されました」と出たら、「詳細情報」→「実行」を押します
   （署名のない個人開発のアプリに出る表示です）。
3. 使う翻訳モデルを選んで「インストール」を押します。標準の 2B なら、ダウンロードは合計で約3GBです。

管理者権限は不要で、`%LOCALAPPDATA%\Programs\PLaMoPaperReader` に入ります。Python、llama.cpp、
PLaMo 3 Translate はインストーラーがダウンロードし、デスクトップとスタートメニューにショートカットを作ります。
途中で止まっても、もう一度実行すれば続きから再開します。モデルを後から足すときも、同じインストーラーで追加を選びます。
アンインストールは、Windows の「設定」→「アプリ」→「インストールされているアプリ」から行います。
タスクマネージャーには「PLaMo 論文リーダー」の名前で表示されます。説明欄とアイコンを書き換えた Python
（`.venv\Scripts\PLaMoPaperReader.exe`）でアプリを動かしています。

### コマンドで入れる

1. [uv](https://docs.astral.sh/uv/)（Python の管理ツール）を入れます。PowerShell で
   `winget install --id astral-sh.uv -e` を実行し、PowerShell を開き直します。
2. このリポジトリをダウンロードします（緑の「Code」→「Download ZIP」で展開するか、`git clone`）。
3. フォルダで PowerShell を開き、セットアップを実行します。

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\setup.ps1
   ```

   Python 環境、llama.cpp、PLaMo 3 Translate 2B（約1.8GB）を用意し、デスクトップとスタートメニューに
   ショートカットを作ります。モデルは `-Models 0.8b,2b,8b` で選べます（0.8B は約0.6GB、8B は約5.3GB）。
   GPU のない PC では `-Cpu` を付けてください。

初回の翻訳では、BabelDOC がレイアウト解析用のデータとフォントをダウンロードします。2 回目以降は、
PLaMo を使う限り論文を外部に送らずに PC 内で翻訳します。

## 起動

デスクトップかスタートメニューの「PLaMo論文リーダー」を開きます。

- ショートカットを作り直すとき: `powershell -ExecutionPolicy Bypass -File tools\make_shortcuts.ps1`
- ブラウザで開くとき: `.venv\Scripts\python.exe app.py --browser`

### タスクバーに固定

スタートメニューで「PLaMo論文リーダー」を右クリックし、「詳細」→「タスクバーにピン留めする」を選びます。
論文と「訳」の専用アイコンで表示します。最小化している間も翻訳やiPad共有は続きます。
ウィンドウを閉じるとアプリは終了します。Windowsへのログイン時に自動起動する設定ではありません。

## できること

- **翻訳**: PDFをドロップするかボタンで選ぶと翻訳が始まります。同じ論文を別のエンジンでも訳して見比べられます。
  - 壊れたPDFやパスワード付きPDFは登録前に案内します。
  - 同じ論文・エンジンへの重複した翻訳依頼は一度だけ受け付けます。
  - モデル起動中の中止にも対応し、中止後の古い処理が再試行の進捗を上書きしないようにしています。
- **読書モード**: 本文を1段で読みやすく流し直します。図は画像で、数式は元ページの切り抜きで表示します。
  - 背景（白・セピア・黒）、書体（明朝・ゴシック）、文字の大きさ・行間・幅を変えられます
  - 段落をタップすると原文が出ます。「原文を併記する」で全段落に原文を並べます
  - **集中モード**（ボタンか F キー）: 上のバーを隠し、いま読んでいる段落以外を薄くします
  - 読んだ位置は自動で覚えます
- **読み上げ**: 日本語の声で段落ごとに読み上げ、読んでいる段落を強調します。速さと声を選べます
  （Windows では Haruka / Ayumi / Nanami など、iPad では Kyoko など、端末に入っている声を使います）。
  - 停止後は「再開」で、読み終えていない短い区切りの先頭から再開します。音声エラー時も未読の文を飛ばしません。
  - 長文は短く区切って読み上げます。声や速度を変更すると、読みかけの区切りを読み直します。
- **PDF / 対訳**: 翻訳済みPDFと、原文と訳文を並べたPDFをそのまま開けます。
  章・節のしおり（目次）を日本語の見出しで付け、開いたときに展開して表示します。

読書モードの見出しは、原文PDFの目次と書式（番号付きの太字・斜体など）をもとに判定します。著者の連絡先や
DOI・受理日などの出版情報は本文から除き、脚注は途中に挟まず、続きの段落の後にまとめます。
段や改ページ、図・図の説明をまたいで途中で切れた文は、1つの段落につなげます。枠で囲まれた文字の多い図
（雑誌風の論文のインフォグラフィック）は、中の文字を本文に並べず、図として画像で表示します。
表も行と列が崩れないよう画像で表示し、表題の直後に置きます（表題の下の横線〜二重線の範囲、または罫線で囲まれた範囲）。
以前の版で翻訳した論文も、開いたときに一度だけ自動で作り直します。
- **iPadで読む**: 「iPadで読む」→「共有を開始」でQRコードが出ます。同じWi‑FiのiPadで読み取ると、
  Safariでライブラリ・読書モード・読み上げが使えます。共有ボタンで止めるか、アプリを閉じると止まります。

## 翻訳エンジン

| エンジン | 置き場所 | 必要な環境変数 | データの扱い |
| --- | --- | --- | --- |
| PLaMo 0.8B / 2B / 8B | PC内 | なし | 外部に送らない |
| DeepL API（Pro） | DeepL | `DEEPL_API_KEY` | Pro版は翻訳後に削除、学習に使わない（Free版のキー `…:fx` は条件を確認） |
| Azure Translator | Microsoft | `AZURE_TRANSLATOR_KEY`（`AZURE_TRANSLATOR_REGION`・`AZURE_TRANSLATOR_ENDPOINT` は任意） | 保存しない（No Trace）、学習に使わない |
| Google Cloud Translation | Google Cloud | `GOOGLE_CLOUD_TRANSLATE_API_KEY` | 学習に使わず、第三者に共有しない |
| Gemini | Google | `GEMINI_API_KEY` | 有料枠は製品改善に使わない。無料枠は使われることがある |

データの扱いは各社の公開情報の要約で、アプリの設定画面に公式ページへのリンクがあります。契約や枠によって変わるため、
大事な論文を送る前には公式の条件を確認してください。

**APIキーは環境変数で渡します。** コードや設定ファイルには書きません。PowerShell で次のように設定すると、
アプリを再起動しなくても設定画面を開き直すだけで反映されます。

```powershell
setx DEEPL_API_KEY "キー"
setx AZURE_TRANSLATOR_KEY "キー"
setx AZURE_TRANSLATOR_REGION "japaneast"
setx GOOGLE_CLOUD_TRANSLATE_API_KEY "キー"
setx GEMINI_API_KEY "キー"
```

Gemini のモデルは設定画面で、APIから取れる一覧から選ぶか、モデル名を直接入力できます（既定は `gemini-3.8-flash`）。

## 参考文献

「参考文献も翻訳する」のチェックを外すと（既定）、参考文献リストの項目は原文のまま残ります。
BabelDOC が翻訳に送る段落ごとに、著者名と発行年の書き出し、姓＋イニシャルの並び、DOI、番号つき（IEEE形式）などから
参考文献かどうかを判定します（`paperapp/references.py`、確認用 `tests/test_references.py`）。

## 翻訳エンジンを足すには

`paperapp/registry.py` の `Engine` を継承したクラスを作り、`ENGINES` に加えます。翻訳APIなら `MTEngine` を継承し、
`paperapp/mt_translators.py` に `HtmlMTTranslator` を継承した翻訳部品（`call_api` だけ書けばよい）を足します。
BabelDOC が本文中の太字・数式に付ける目印は、最初から「訳さない」印つきのHTMLタグにしてあるので、HTML翻訳に対応したAPIならそのまま使えます。

## 用語集

`glossary.csv` に `source,target` の形で訳語を書くと、その語を含む段落にだけ用語指定を付けて訳します（PLaMo と Gemini。DeepL・Azure・Google には効きません）。

## コマンドで使う

```powershell
.\.venv\Scripts\python.exe run_plamo.py 論文.pdf --engine plamo-8b --pages 1-3
```

PDF を `translate.bat` にドラッグ＆ドロップしても訳せます（2B、結果は `output` フォルダ）。

## 構成

- `app.py`: アプリの入口（pywebview の窓）。二重起動するとすでに開いているアプリを使います
- `paperapp/server.py`: 画面・iPad共有用のHTTPサーバー、ライブラリ（`library/`）、翻訳ジョブの順番待ち
- `paperapp/worker.py`: BabelDOC を別プロセスで動かし、進み具合を返す。1件も訳せなかったときは失敗として扱う
- `paperapp/registry.py`: 翻訳エンジンの一覧（名前・必要な環境変数・データの扱い・BabelDOC への組み込み方）
- `paperapp/translators.py`: PLaMo 用・Gemini 用の翻訳部品と、参考文献を原文のまま残す仕組み
- `paperapp/mt_translators.py`: DeepL / Azure / Google の翻訳部品
- `paperapp/envkeys.py`: 環境変数（Windows では登録済みのユーザー環境変数も）からキーを読む
- `paperapp/engines.py`: llama-server の起動・モデルの切り替え
- `paperapp/reading.py`: 翻訳済みPDFから読書モード用の段落・見出し・図・数式を取り出す
- `paperapp/static/`: 画面（HTML / CSS / JavaScript）

## ライセンス

このアプリのソースコードは [GNU Affero General Public License v3.0](LICENSE)（AGPL-3.0）で公開します。
レイアウト処理に使う [BabelDOC](https://github.com/funstory-ai/BabelDOC) が AGPL-3.0 のため、それに合わせています。

翻訳モデルの PLaMo 3 Translate（0.8B / 2B / 8B）はこのリポジトリに含まれていません。各自が Hugging Face の
[pfnet](https://huggingface.co/pfnet) から入手し、[PLaMo Community License](https://plamo.preferredai.jp/info/plamo-community-license-ja)
に従って使ってください。

- 個人の学習・趣味や、学術などの非商用の利用は無料で、PFNへの事前登録も不要です。
- 商用利用は、利用者（関係会社を含む）の直近事業年度の売上が10億円以下なら、PFNの登録フォームで届け出れば無料です。
  10億円を超える場合は、PFNとの個別の契約が必要です。
- 商用利用では「Built with PLaMo」の表示が求められます。

**Built with PLaMo**

llama.cpp（MIT）とフォントはこのリポジトリに含まず、セットアップや実行の際に取得します。
