<#
PLaMo 論文リーダーのセットアップ（Windows 10/11）。

  powershell -ExecutionPolicy Bypass -File tools\setup.ps1                 # 2B モデル
  powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Models 0.8b,2b,8b
  powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Cpu            # GPU なしの PC

Python 環境（.venv）、llama.cpp（llama\）、PLaMo 3 Translate の GGUF（models\）を用意し、
デスクトップとスタートメニューにショートカットを作ります。済んでいる手順は飛ばします。
#>
param(
    [ValidateSet('0.8b', '2b', '8b')]
    [string[]]$Models = @('2b'),
    [switch]$Cpu,
    [switch]$NoShortcuts
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path $PSScriptRoot -Parent
$llamaBuild = 'b12211'

function Step($text) { Write-Host ''; Write-Host "== $text" -ForegroundColor Cyan }

function Download($url, $dest) {
    $tmp = "$dest.part"
    & curl.exe -L --fail --retry 3 -C - -o $tmp $url
    if ($LASTEXITCODE -ne 0) { throw "ダウンロードに失敗しました: $url" }
    Move-Item -LiteralPath $tmp -Destination $dest -Force
}

Step 'uv（Python の管理ツール）を確認'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv が見つかりません。先に「winget install --id astral-sh.uv -e」でインストールし、PowerShell を開き直してから、もう一度実行してください。'
}

Step 'Python 環境（.venv）を準備'
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    & uv venv --python 3.11 (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 環境を作れませんでした。' }
}
& uv pip install --python $py -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'パッケージをインストールできませんでした。' }

Step "llama.cpp $llamaBuild を準備"
$llamaDir = Join-Path $root 'llama'
if (-not (Test-Path (Join-Path $llamaDir 'llama-server.exe'))) {
    $kind = if ($Cpu) { 'cpu' } else { 'vulkan' }
    $zip = Join-Path $env:TEMP "llama-$llamaBuild-$kind.zip"
    Download "https://github.com/ggml-org/llama.cpp/releases/download/$llamaBuild/llama-$llamaBuild-bin-win-$kind-x64.zip" $zip
    Expand-Archive -LiteralPath $zip -DestinationPath $llamaDir -Force
    # Some builds wrap the files in a subfolder.
    $exe = Get-ChildItem $llamaDir -Recurse -Filter 'llama-server.exe' | Select-Object -First 1
    if (-not $exe) { throw 'llama-server.exe が見つかりませんでした。' }
    if ($exe.DirectoryName -ne $llamaDir) {
        Get-ChildItem $exe.DirectoryName | Move-Item -Destination $llamaDir -Force
    }
    Remove-Item -LiteralPath $zip -Force
}

Step 'PLaMo 3 Translate モデルを準備'
$modelDir = Join-Path $root 'models'
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
foreach ($m in $Models) {
    $file = "plamo-3-translate-$m-Q4_K_M.gguf"
    $dest = Join-Path $modelDir $file
    if (Test-Path $dest) { Write-Host "$file は準備済みです。"; continue }
    Write-Host "$file をダウンロードします（PLaMo Community License に従って利用してください）。"
    Download "https://huggingface.co/pfnet/plamo-3-translate-$m-GGUF/resolve/main/$file" $dest
}

if (-not $NoShortcuts) {
    Step 'ショートカットを作成'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'make_shortcuts.ps1')
}

Write-Host ''
Write-Host 'セットアップが終わりました。「PLaMo論文リーダー」を開いてください。' -ForegroundColor Green
Write-Host '初回の翻訳では、BabelDOC がレイアウト解析用のデータとフォントをダウンロードします。'
