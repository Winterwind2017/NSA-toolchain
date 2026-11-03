# 一键回归：内核单测 + 指定 kit 的真机验收
#
#   .\scripts\ci.ps1                 # 单测 + 全部 kit（sw/nx/acad/gx/codesys/autoshop）
#   .\scripts\ci.ps1 -Kits sw,acad   # 只跑这两家
#   .\scripts\ci.ps1 -SkipAcceptance # 只跑单测（不需要任何软件开着）
#   .\scripts\ci.ps1 -SkipApps       # 跳过需要重型程序的组（gx / autoshop）
#
# 退出码 0 = 全绿；非 0 = 有失败，可直接接进计划任务或 CI。

param(
    [string[]]$Kits = @("sw", "nx", "acad", "gx", "codesys", "autoshop"),
    [switch]$SkipAcceptance,
    [switch]$SkipApps
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = "C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$env:PYTHONPATH = $root
$env:PYTHONIOENCODING = "utf-8"

Write-Host "=== 1/2 内核单测 ===" -ForegroundColor Cyan
Push-Location $root
& $py -m unittest discover -s tests 2>&1 | Select-Object -Last 4
$unitOk = ($LASTEXITCODE -eq 0)
Pop-Location

if (-not $unitOk) {
    Write-Host "单测失败，先修内核再跑验收。" -ForegroundColor Red
    exit 1
}

if ($SkipAcceptance) {
    Write-Host "单测通过（已跳过验收）。" -ForegroundColor Green
    exit 0
}

if ($SkipApps) {
    $Kits = $Kits | Where-Object { $_ -notin @("gx", "autoshop") }
}

Write-Host "`n=== 2/2 真机验收：$($Kits -join ', ') ===" -ForegroundColor Cyan
$accArgs = @("-m", "kitmcp.acceptance")
foreach ($k in $Kits) { $accArgs += @("--kit", $k) }

Push-Location $root
& $py @accArgs 2>&1 | Select-Object -Last 40
$accOk = ($LASTEXITCODE -eq 0)
Pop-Location

if ($accOk) {
    Write-Host "`n全绿。" -ForegroundColor Green
    exit 0
}
Write-Host "`n有失败项，见上面的报告路径。" -ForegroundColor Red
exit 1
