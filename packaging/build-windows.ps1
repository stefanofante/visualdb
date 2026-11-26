$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$runtime = Join-Path $root "build/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124701" -OutFile $runtime
$signature = Get-AuthenticodeSignature $runtime
if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)') {
    throw "The WebView2 standalone installer lacks a valid Microsoft signature."
}
$tool = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6/ISCC.exe"
if (-not (Test-Path $tool)) { $tool = (Get-Command ISCC.exe -ErrorAction Stop).Source }
$version = python -c "from importlib.metadata import version; print(version('dbvisual'))"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $tool "/DAppVersion=$version" "packaging/windows.iss"
exit $LASTEXITCODE
