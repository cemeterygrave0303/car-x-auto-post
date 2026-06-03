[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

$git = $null
$paths = @("C:\Program Files\Git\bin\git.exe","C:\Program Files (x86)\Git\bin\git.exe")
foreach ($p in $paths) { if (Test-Path $p) { $git = $p; break } }
if (-not $git) {
    $g = Get-Command git -ErrorAction SilentlyContinue
    if ($g) { $git = $g.Source }
}
if (-not $git) { Write-Host "git not found"; exit 1 }

Write-Host "--- Changed files ---"
& $git status --short

$changes = & $git status --porcelain
if (-not $changes) { Write-Host "No changes."; exit 0 }

& $git add -A
$ts = Get-Date -Format "yyyy-MM-dd HH:mm"
& $git commit -m "update: $ts"
& $git push

Write-Host "--- Push complete! ---"
