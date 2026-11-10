$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Add-Type -Path (Join-Path $PSScriptRoot 'ShortcutIdentity.cs')

# Build the launcher so Task Manager shows the app name instead of "Python".
$launcher = Join-Path $root 'PLaMoPaperReader.exe'
$launcherSrc = Join-Path $root 'installer\Launcher.cs'
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if ((Test-Path $launcherSrc) -and (Test-Path $csc) -and
    (-not (Test-Path $launcher) -or (Get-Item $launcherSrc).LastWriteTime -gt (Get-Item $launcher).LastWriteTime)) {
  & $csc /nologo /target:winexe /optimize+ /codepage:65001 ('/out:' + $launcher) ('/win32icon:' + (Join-Path $root 'assets\app.ico')) /r:System.Windows.Forms.dll $launcherSrc | Out-Null
}

$sh = New-Object -ComObject WScript.Shell
$targets = @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ''))
foreach ($dir in $targets) {
  $lnk = $sh.CreateShortcut((Join-Path $dir 'PLaMo論文リーダー.lnk'))
  if (Test-Path $launcher) {
    $lnk.TargetPath = $launcher
    $lnk.Arguments = ''
  } else {
    $lnk.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
    $lnk.Arguments = '"' + (Join-Path $root 'app.py') + '"'
  }
  $lnk.WorkingDirectory = $root
  $lnk.IconLocation = (Join-Path $root 'assets\app.ico') + ',0'
  $lnk.Description = 'PLaMo / Gemini で論文PDFを翻訳して読むアプリ'
  $lnk.Save()
  [ShortcutIdentity]::Set((Join-Path $dir 'PLaMo論文リーダー.lnk'), 'PLaMo.PaperReader.Desktop')
  Write-Output (Join-Path $dir 'PLaMo論文リーダー.lnk')
}
