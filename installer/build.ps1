# Build installer\dist\PLaMoPaperReader-Setup.exe with the .NET Framework compiler built into Windows.
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path $here -Parent
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$dist = Join-Path $here 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$cscArgs = @(
    '/nologo', '/target:winexe', '/optimize+', '/codepage:65001',
    ('/out:' + (Join-Path $dist 'PLaMoPaperReader-Setup.exe')),
    ('/win32icon:' + (Join-Path $root 'assets\app.ico')),
    ('/win32manifest:' + (Join-Path $here 'app.manifest')),
    '/r:System.IO.Compression.dll', '/r:System.IO.Compression.FileSystem.dll',
    '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll',
    (Join-Path $here 'Setup.cs')
)
& $csc @cscArgs
if ($LASTEXITCODE -ne 0) { throw 'build failed' }
Get-Item (Join-Path $dist 'PLaMoPaperReader-Setup.exe') | Select-Object FullName, Length

