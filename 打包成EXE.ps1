param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Path dist -Force | Out-Null

# Build the parser as a hidden one-file worker, then embed it in a native
# Windows Forms shell.  The distributed result remains one EXE.
& $Python -m PyInstaller --noconfirm --clean --onefile --console `
  --name social_article_parser_worker --paths src `
  --distpath native_build --workpath worker_build parser_worker_entry.py
if ($LASTEXITCODE -ne 0) {
  throw "Python 解析组件打包失败。"
}

$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $csc)) {
  throw "未找到 Windows .NET Framework 编译器。"
}

& $csc /nologo /target:winexe /platform:x64 /optimize+ `
  /out:dist\social_article_parser.exe `
  /r:System.Windows.Forms.dll /r:System.Drawing.dll `
  /resource:native_build\social_article_parser_worker.exe,ParserWorker native_launcher.cs
if ($LASTEXITCODE -ne 0) {
  throw "Windows 桌面程序编译失败。"
}

Remove-Item -LiteralPath native_build, worker_build, social_article_parser_worker.spec -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Build complete: dist\social_article_parser.exe"
