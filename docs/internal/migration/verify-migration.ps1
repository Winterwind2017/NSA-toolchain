# 迁移校验：13 个老路径是否都正确指向 monorepo，内容是否一致，git 是否干净
#
#   .\docs\internal\migration\verify-migration.ps1
#
# 退出码 0 = 全部 OK。

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$fail = 0

$links = [ordered]@{
    "D:\bililive\solidworks-agent-kit"     = "kernels\sw"
    "D:\bililive\acadkit"                  = "kernels\acad"
    "D:\bililive\nxkit"                    = "kernels\nx"
    "D:\bililive\gxkit"                    = "kernels\gx"
    "D:\bililive\codesyskit"               = "kernels\codesys"
    "D:\bililive\autoshopkit"              = "kernels\autoshop"
    "D:\bililive\ww-solidworks-automation" = "skills\ww-solidworks-automation"
    "D:\bililive\ww-autocad-automation"    = "skills\ww-autocad-automation"
    "D:\bililive\ww-nx-automation"         = "skills\ww-nx-automation"
    "D:\bililive\ww-gxworks-automation"    = "skills\ww-gxworks-automation"
    "D:\bililive\ww-codesys-automation"    = "skills\ww-codesys-automation"
    "D:\bililive\ww-autoshop-automation"   = "skills\ww-autoshop-automation"
}

Write-Host "=== 1) 老路径 → monorepo 联接 ===" -ForegroundColor Cyan
foreach ($old in $links.Keys) {
    $target = Join-Path $root $links[$old]
    if (-not (Test-Path $old)) { Write-Host ("  FAIL {0} 不存在" -f $old) -ForegroundColor Red; $fail++; continue }
    $item = Get-Item $old -Force
    # junction 的 Resolve-Path 不会跟到目标，必须读 Target
    $linkTarget = $item.Target
    if ($linkTarget -is [array]) { $linkTarget = $linkTarget[0] }
    $expect = [System.IO.Path]::GetFullPath($target).TrimEnd("\")
    $got = if ($linkTarget) { [System.IO.Path]::GetFullPath($linkTarget).TrimEnd("\") } else { "" }
    if ($item.LinkType -and $got -ieq $expect) {
        Write-Host ("  OK   {0} → {1}" -f (Split-Path $old -Leaf), $links[$old]) -ForegroundColor Green
    }
    else {
        Write-Host ("  FAIL {0} 联接={1} 实际={2} 期望={3}" -f $old, $item.LinkType, $got, $expect) -ForegroundColor Red
        $fail++
    }
}

Write-Host "`n=== 2) hub 现状 ===" -ForegroundColor Cyan
$hubOld = "D:\bililive\nsa-mcp-hub"
$hubNew = Join-Path $root "hub"
$o = Get-Item $hubOld -Force
$n = Get-Item $hubNew -Force
function Show-Link($path, $item) {
    $t = $item.Target
    if ($t -is [array]) { $t = $t -join ", " }
    if (-not $t) { $t = "(真实目录)" }
    Write-Host ("  {0}: 联接={1} → {2}" -f $path, $item.LinkType, $t)
}
Show-Link $hubOld $o
Show-Link $hubNew $n
if ($o.LinkType -or -not $n.LinkType) {
    Write-Host "  WARN hub 联接方向反了（应为：老路径=联接，新路径=真实目录）" -ForegroundColor Yellow
}
else {
    Write-Host "  OK   hub 方向正确（老路径=联接，新路径=真实目录）" -ForegroundColor Green
}
$hubPy = Join-Path $hubOld "nsa_mcp_hub\__init__.py"
if (Test-Path $hubPy) { Write-Host "  OK   hub 包可读" -ForegroundColor Green }
else { Write-Host "  FAIL hub 包读不到：$hubPy" -ForegroundColor Red; $fail++ }

Write-Host "`n=== 3) monorepo git 状态 ===" -ForegroundColor Cyan
$dirty = @(git -C $root status --short 2>$null)
if ($dirty.Count -eq 0) { Write-Host "  OK   git 干净" -ForegroundColor Green }
else { Write-Host ("  WARN 有 {0} 项未提交：" -f $dirty.Count) -ForegroundColor Yellow; $dirty | Select-Object -First 8 | ForEach-Object { "     $_" } }

$tracked = @(git -C $root ls-files 2>$null).Count
Write-Host ("  跟踪文件 {0} 个，提交 {1} 个" -f $tracked, @(git -C $root rev-list --count HEAD 2>$null)[0])

Write-Host "`n=== 4) 内核目录结构抽查 ===" -ForegroundColor Cyan
foreach ($k in "sw", "acad", "nx", "gx", "codesys", "autoshop") {
    $p = Join-Path $root "kernels\$k"
    $hasCfg = (Test-Path (Join-Path $p "pyproject.toml")) -or (Test-Path (Join-Path $p "README.md"))
    if ($hasCfg) { Write-Host ("  OK   kernels\{0}" -f $k) -ForegroundColor Green }
    else { Write-Host ("  FAIL kernels\{0} 缺 pyproject/README" -f $k) -ForegroundColor Red; $fail++ }
}

Write-Host ""
if ($fail -eq 0) { Write-Host "全部通过。" -ForegroundColor Green; exit 0 }
Write-Host ("有 {0} 项失败。" -f $fail) -ForegroundColor Red
exit 1
