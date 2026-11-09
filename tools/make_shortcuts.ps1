$root = 'C:\myproject\plamo-babeldoc'
$sh = New-Object -ComObject WScript.Shell
$targets = @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ''))
foreach ($dir in $targets) {
  $lnk = $sh.CreateShortcut((Join-Path $dir 'PLaMo論文リーダー.lnk'))
  $lnk.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
  $lnk.Arguments = 'app.py'
  $lnk.WorkingDirectory = $root
  $lnk.IconLocation = (Join-Path $root 'assets\app.ico') + ',0'
  $lnk.Description = 'PLaMo / Gemini で論文PDFを翻訳して読むアプリ'
  $lnk.Save()
  Write-Output (Join-Path $dir 'PLaMo論文リーダー.lnk')
}
