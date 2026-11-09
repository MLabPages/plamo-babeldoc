# PLaMo 3 Translate を PC 上で動かす llama.cpp サーバーを起動する（起動済みなら何もしない）
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
try {
    Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 2 | Out-Null
    Write-Host '翻訳サーバーは起動済みです。'
    exit 0
} catch {}

$model = Join-Path $root 'models\plamo-3-translate-2b-Q4_K_M.gguf'
Start-Process -FilePath (Join-Path $root 'llama\llama-server.exe') -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $root 'server.log') -RedirectStandardError (Join-Path $root 'server.err.log') `
    -ArgumentList '-m', $model, '--host', '127.0.0.1', '--port', '8090', '-ngl', '99', '-c', '16384', '-np', '4', '--jinja', '--alias', 'plamo-3-translate-2b'

Write-Host '翻訳サーバーを起動しています...'
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 1
    try {
        Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 2 | Out-Null
        Write-Host '翻訳サーバーの準備ができました。'
        exit 0
    } catch {}
}
Write-Error '翻訳サーバーが起動しませんでした。server.err.log を確認してください。'
