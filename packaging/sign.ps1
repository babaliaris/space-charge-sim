# Sign Windows files with a code-signing certificate (Authenticode, SHA-256, timestamped).
# Used by the GitHub workflow only when the repository secrets WINDOWS_CERT_PFX (the .pfx file, base64)
# and WINDOWS_CERT_PASSWORD exist.   Usage:  pwsh packaging/sign.ps1 file1.exe [file2.exe ...]
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Files)
$ErrorActionPreference = "Stop"

$pfx = Join-Path $env:RUNNER_TEMP "codesign.pfx"
[IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:WINDOWS_CERT_PFX))
try {
    $signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $signtool) { throw "signtool.exe not found" }
    foreach ($f in $Files) {
        & $signtool.FullName sign /f $pfx /p $env:WINDOWS_CERT_PASSWORD /fd SHA256 `
            /tr http://timestamp.digicert.com /td SHA256 /d "Space-Charge Simulator" $f
        if ($LASTEXITCODE -ne 0) { throw "signing failed: $f" }
        & $signtool.FullName verify /pa $f
    }
}
finally {
    Remove-Item $pfx -Force -ErrorAction SilentlyContinue
}
