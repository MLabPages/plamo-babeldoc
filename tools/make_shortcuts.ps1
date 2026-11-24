$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Add-Type -Path (Join-Path $PSScriptRoot 'ShortcutIdentity.cs')

# Task Manager names the window's process from its file description, so run the app with a
# copy of pythonw.exe whose description and icon say "MLab論文リーダー".
$appExe = Join-Path $root '.venv\Scripts\PLaMoPaperReader.exe'
try { & (Join-Path $PSScriptRoot 'brand.ps1') } catch { Write-Warning $_ }
Remove-Item -LiteralPath (Join-Path $root 'PLaMoPaperReader.exe') -Force -ErrorAction SilentlyContinue  # 1.0.1 の起動用プログラム

$sh = New-Object -ComObject WScript.Shell
$targets = @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ''))
foreach ($dir in $targets) {
  $lnk = $sh.CreateShortcut((Join-Path $dir 'MLab論文リーダー.lnk'))
  $lnk.TargetPath = if (Test-Path $appExe) { $appExe } else { Join-Path $root '.venv\Scripts\pythonw.exe' }
  $lnk.Arguments = '"' + (Join-Path $root 'app.py') + '"'
  $lnk.WorkingDirectory = $root
  $lnk.IconLocation = (Join-Path $root 'assets\app.ico') + ',0'
  $lnk.Description = 'PLaMo / Gemini で論文PDFを翻訳して読むアプリ'
  $lnk.Save()
  [ShortcutIdentity]::Set((Join-Path $dir 'MLab論文リーダー.lnk'), 'PLaMo.PaperReader.Desktop')
  # Remove the previous name only when it points to this installation.
  $oldPath = Join-Path $dir ('PLaMo' + '論文リーダー.lnk')
  if (Test-Path -LiteralPath $oldPath) {
    $old = $sh.CreateShortcut($oldPath)
    if ($old.WorkingDirectory -eq $root -and $old.Arguments -eq $lnk.Arguments) {
      Remove-Item -LiteralPath $oldPath
    }
  }
  Write-Output (Join-Path $dir 'MLab論文リーダー.lnk')
}
