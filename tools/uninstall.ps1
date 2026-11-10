# PLaMo 論文リーダーのアンインストール（Windows の「アプリ」一覧から呼ばれる）。
param([switch]$Quiet, [switch]$RemoveLibrary)
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
$root = Split-Path $PSScriptRoot -Parent
$title = 'PLaMo 論文リーダー'
Set-Location $env:TEMP

if (-not $Quiet) {
    $ok = [System.Windows.Forms.MessageBox]::Show("PLaMo 論文リーダーをアンインストールしますか？`n`n$root", $title, 'YesNo', 'Question')
    if ($ok -ne 'Yes') { exit 1 }
    $lib = Join-Path $root 'library'
    if ((Test-Path $lib) -and (Get-ChildItem $lib -ErrorAction SilentlyContinue)) {
        $ans = [System.Windows.Forms.MessageBox]::Show("翻訳した論文（ライブラリ）も削除しますか？`n「いいえ」を選ぶと library フォルダだけ残します。", $title, 'YesNo', 'Question')
        $RemoveLibrary = ($ans -eq 'Yes')
    } else { $RemoveLibrary = $true }
}

# このフォルダから起動したアプリと翻訳エンジンだけを止める
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) -or
    ($_.CommandLine -and $_.CommandLine.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.Name -match '^pythonw?\.exe$')
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800

# このフォルダを指すショートカットだけを消す
$sh = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $lnk = Join-Path $dir 'PLaMo論文リーダー.lnk'
    if ((Test-Path $lnk) -and $sh.CreateShortcut($lnk).WorkingDirectory -eq $root) { Remove-Item -LiteralPath $lnk -Force }
}

Get-ChildItem -LiteralPath $root -Force | Where-Object { $RemoveLibrary -or $_.Name -ne 'library' } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
if ($RemoveLibrary) {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PLaMoPaperReader' -Recurse -Force -ErrorAction SilentlyContinue

if (-not $Quiet) {
    $msg = if ($RemoveLibrary) { 'アンインストールしました。' } else { "アンインストールしました。翻訳した論文は次の場所に残しています。`n$root\library" }
    [System.Windows.Forms.MessageBox]::Show($msg, $title) | Out-Null
}

