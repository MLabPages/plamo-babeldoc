# .venv\Scripts\PLaMoPaperReader.exe（説明欄とアイコンをアプリ名にした Python）を作る。
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$version = '1.0.2'
$cfg = Join-Path $root '.venv\pyvenv.cfg'
if (-not (Test-Path $cfg)) { throw 'Python 環境（.venv）がありません。' }
$homeLine = Get-Content $cfg | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
$pyHome = ($homeLine -split '=', 2)[1].Trim()
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$tool = Join-Path $env:TEMP 'plamo-paper-reader-brand.exe'
& $csc /nologo /target:exe /optimize+ /codepage:65001 ('/out:' + $tool) (Join-Path $root 'installer\Brand.cs') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'brand tool build failed' }
& $tool (Join-Path $root '.venv\Scripts') $pyHome (Join-Path $root 'assets\app.ico') 'PLaMoPaperReader.exe' $version
$code = $LASTEXITCODE
Remove-Item -LiteralPath $tool -Force -ErrorAction SilentlyContinue
if ($code -ne 0) { throw 'アプリ名の実行ファイルを作れませんでした。' }

