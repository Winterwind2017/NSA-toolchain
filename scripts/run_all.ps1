# 一键收官：探测已开的应用 → 只跑能跑的 kit → 汇总 + 重算覆盖表
#
#   .\scripts\run_all.ps1                    # 自动：跑"不需要额外拉起重程序"的 kit
#   .\scripts\run_all.ps1 -IncludeHeavy      # 连 nx / ug / gx / autoshop 一起（会拉 NX、抢焦点）
#   .\scripts\run_all.ps1 -Kits sw,acad      # 只跑指定 kit（跳过探测）
#   .\scripts\run_all.ps1 -SkipUnit          # 不跑内核单测
#   .\scripts\run_all.ps1 -NoCoverage        # 不重算覆盖表
#
# 退出码 0 = 全部 PASS/SKIP；1 = 有 FAIL/ERROR 或单测失败。
#
# 设计原则（跟整套工具一致）：**绝不为跑验收去启动应用**。应用没开就 SKIP 并写明原因；
# nxkit / codesys 是例外（前者自己拉 NX，后者是 headless 常驻服务）。

param(
    [string[]]$Kits = @(),
    [switch]$IncludeHeavy,
    [switch]$SkipUnit,
    [switch]$NoCoverage,
    [switch]$NoKeepEvidence,
    [string]$ReportRoot = "_runs"
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$py = "C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$env:PYTHONPATH = $root
$env:PYTHONIOENCODING = "utf-8"
Set-Location $root

# ── 应用探测表：kit → 进程名候选 + 是否"重"（拉大程序/抢焦点）──────────────
$KIT_APPS = [ordered]@{
    sw       = @{ procs = @("SLDWORKS");                     heavy = $false; why = "SolidWorks 2025" }
    acad     = @{ procs = @("acad");                          heavy = $false; why = "AutoCAD 2025" }
    codesys  = @{ procs = @(); heavy = $false; why = "headless 常驻服务（自动起）" }
    eplan    = @{ procs = @("Eplan", "EPLAN");                heavy = $false; why = "EPLAN 2.9（需已打开工程）" }
    catia    = @{ procs = @("CNEXT", "CATIA");                heavy = $false; why = "CATIA V5（本机未装）" }
    nx       = @{ procs = @(); heavy = $true;  why = "nxkit 会自己拉起 NX" }
    ug       = @{ procs = @("ugraf");                         heavy = $true;  why = "NX + .NET 桥" }
    gx       = @{ procs = @("GXW3", "GX Works3");             heavy = $true;  why = "GX Works3（抢焦点）" }
    autoshop = @{ procs = @("AutoShop", "InoAutoShop");       heavy = $true;  why = "AutoShop（MFC，抢焦点）" }
}

function Test-AppRunning {
    param([string[]]$Names)
    foreach ($n in $Names) {
        $p = Get-Process -Name $n -ErrorAction SilentlyContinue
        if ($p) { return $true }
    }
    return $false
}

# ── 1. 内核单测 ────────────────────────────────────────────────────────────
$unitOk = $true
if (-not $SkipUnit) {
    Write-Host "`n=== 1/3 内核单测 ===" -ForegroundColor Cyan
    & $py -m unittest discover -s tests 2>&1 | Select-Object -Last 4
    $unitOk = ($LASTEXITCODE -eq 0)
    if ($unitOk) { Write-Host "单测通过" -ForegroundColor Green }
    else { Write-Host "单测失败（继续跑验收，但退出码会是 1）" -ForegroundColor Yellow }
}

# ── 2. 选 kit ──────────────────────────────────────────────────────────────
Write-Host "`n=== 2/3 选择要跑的 kit ===" -ForegroundColor Cyan
$plan = @()
if ($Kits.Count -gt 0) {
    foreach ($k in $Kits) {
        $info = $KIT_APPS[$k]
        if (-not $info) { Write-Host ("  ? {0,-9} 未知 kit，跳过" -f $k) -ForegroundColor Yellow; continue }
        $plan += [pscustomobject]@{ kit = $k; run = $true; note = "手动指定" }
    }
}
else {
    foreach ($k in $KIT_APPS.Keys) {
        $info = $KIT_APPS[$k]
        $running = if ($info.procs.Count -gt 0) { Test-AppRunning -Names $info.procs } else { $true }
        if ($info.heavy -and -not $IncludeHeavy) {
            $plan += [pscustomobject]@{ kit = $k; run = $false; note = "重（-$IncludeHeavy 未开）: $($info.why)" }
        }
        elseif (-not $running) {
            $plan += [pscustomobject]@{ kit = $k; run = $false; note = "未运行: $($info.why)" }
        }
        else {
            $plan += [pscustomobject]@{ kit = $k; run = $true; note = $info.why }
        }
    }
}
foreach ($row in $plan) {
    $mark = if ($row.run) { "RUN " } else { "SKIP" }
    $color = if ($row.run) { "Green" } else { "DarkGray" }
    Write-Host ("  {0} {1,-9} {2}" -f $mark, $row.kit, $row.note) -ForegroundColor $color
}

# ── 3. 逐 kit 跑验收 ───────────────────────────────────────────────────────
Write-Host "`n=== 3/3 验收 ===" -ForegroundColor Cyan
if (-not (Test-Path $ReportRoot)) { New-Item -ItemType Directory -Path $ReportRoot | Out-Null }

$summary = @()
foreach ($row in $plan) {
    if (-not $row.run) {
        $summary += [pscustomobject]@{ kit = $row.kit; verdict = "SKIP"; passed = 0; total = 0; seconds = 0; report = "" ; failures = $row.note }
        continue
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $report = Join-Path $root (Join-Path $ReportRoot ("acceptance-{0}-{1}.json" -f $row.kit, $stamp))
    Write-Host ("`n--- {0} ---" -f $row.kit) -ForegroundColor Cyan
    & $py -m nsa_mcp_hub.acceptance --kit $row.kit --quiet --report $report 2>&1 | Select-Object -Last 6
    $code = $LASTEXITCODE

    $passed = 0; $total = 0; $seconds = 0; $skipped = 0; $fails = @()
    if (Test-Path $report) {
        $data = Get-Content $report -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($k in $data.kits) {
            $passed += [int]$k.passed
            $total += [int]$k.total
            $skipped += [int]$k.skipped
            $seconds += [double]$k.seconds
            foreach ($r in $k.results) {
                if ($r.verdict -ne "PASS" -and $r.verdict -ne "SKIP") {
                    $fails += ("{0}[{1}]" -f $r.id, $r.verdict)
                }
            }
        }
    }
    $verdict = if ($code -eq 0) { "PASS" } else { "FAIL" }
    $summary += [pscustomobject]@{
        kit = $row.kit; verdict = $verdict; passed = $passed; total = $total
        seconds = [math]::Round($seconds, 1); report = (Split-Path $report -Leaf)
        failures = (($fails | Select-Object -First 5) -join ", ")
    }
}

# ── 汇总表 ─────────────────────────────────────────────────────────────────
Write-Host "`n================ 汇总 ================" -ForegroundColor Cyan
$summary | Format-Table -AutoSize kit, verdict, passed, total, seconds, failures
$ranPass = @($summary | Where-Object { $_.verdict -eq "PASS" }).Count
$ranFail = @($summary | Where-Object { $_.verdict -eq "FAIL" }).Count
$skippedN = @($summary | Where-Object { $_.verdict -eq "SKIP" }).Count
$totPass = ($summary | Measure-Object -Property passed -Sum).Sum
$totAll = ($summary | Measure-Object -Property total -Sum).Sum
Write-Host ("PASS {0} ｜ FAIL {1} ｜ SKIP {2} ｜ 用例 {3}/{4}" -f $ranPass, $ranFail, $skippedN, $totPass, $totAll)

# ── 覆盖表重算（可选）─────────────────────────────────────────────────────
if (-not $NoCoverage) {
    Write-Host "`n=== 覆盖表重算 ===" -ForegroundColor Cyan
    & $py "scripts\coverage_report.py" --write 2>&1 | Select-Object -Last 12
}

# ── 证据归档（默认做）：把本次报告复制到 _archive/acceptance-<stamp>/ ─────
# 理由：_runs 里的报告会被轮转，覆盖表数字就"凭证据说话"地掉下去。
# 每次收官把报告另存一份，历史证据就不会被吃掉。
if (-not $NoKeepEvidence) {
    $stamp2 = Get-Date -Format "yyyyMMdd-HHmmss"
    $dest = Join-Path $root (Join-Path "_archive" ("acceptance-" + $stamp2))
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    $copied = 0
    foreach ($row in $summary) {
        if (-not $row.report) { continue }
        $src = Join-Path $root (Join-Path $ReportRoot $row.report)
        if (Test-Path $src) { Copy-Item $src -Destination $dest -Force; $copied++ }
    }
    if ($copied -gt 0) {
        Write-Host ("`n证据已归档：_archive/{0}（{1} 份报告）" -f (Split-Path $dest -Leaf), $copied)
    }
}

if ($ranFail -gt 0 -or (-not $unitOk)) { exit 1 }
exit 0
