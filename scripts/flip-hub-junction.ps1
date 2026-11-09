# 把 hub 的联接方向翻正：nsa-mcp-hub（真实目录） → nsa-toolchain\hub（真实目录）
#
# 背景见 docs/MIGRATION.md。迁移当时 D:\bililive\nsa-mcp-hub 被进程占用，
# 只能反过来让 nsa-toolchain\hub 指向它。占用释放后跑本脚本即可翻正：
#
#   .\scripts\flip-hub-junction.ps1            # 试运行（只检查）
#   .\scripts\flip-hub-junction.ps1 -Apply     # 真翻
#
# 安全措施：先把旧目录整份复制到 nsa-toolchain\hub.new，成功后再替换联接。

param([switch]$Apply)

$root = Split-Path -Parent $PSScriptRoot
$old = "D:\bililive\nsa-mcp-hub"
$new = Join-Path $root "hub"
$stage = Join-Path $root "hub.new"

Write-Host "=== 现状 ===" -ForegroundColor Cyan
$oldItem = Get-Item $old -Force
$newItem = Get-Item $new -Force
Write-Host ("  老路径 {0}: 联接={1} 指向={2}" -f $old, $oldItem.LinkType, $oldItem.Target)
Write-Host ("  新路径 {0}: 联接={1} 指向={2}" -f $new, $newItem.LinkType, $newItem.Target)

if ($oldItem.LinkType) {
    Write-Host "老路径已经是联接（可能已翻正过），无需操作。" -ForegroundColor Green
    exit 0
}
if (-not $newItem.LinkType) {
    Write-Host "新路径不是联接（可能已翻正过），无需操作。" -ForegroundColor Green
    exit 0
}

# 试探：老目录能否改名（能改名说明占用已释放）
$probe = $old + ".probe"
try {
    Rename-Item $old $probe -ErrorAction Stop
    Rename-Item $probe $old -ErrorAction Stop
    Write-Host "老目录可改名 → 占用已释放" -ForegroundColor Green
}
catch {
    Write-Host "老目录仍被占用，先关掉 DSH/终端再试：$($_.Exception.Message)" -ForegroundColor Yellow
    exit 2
}

if (-not $Apply) {
    Write-Host "`n试运行结束。确认无误后加 -Apply 真翻。" -ForegroundColor Cyan
    exit 0
}

Write-Host "`n=== 开始翻正 ===" -ForegroundColor Cyan
# 1) 把实体目录挪到 nsa-toolchain\hub.new（先删掉联接）
Remove-Item $new -Force
Rename-Item $old $stage   # 同卷改名，瞬间完成
# 2) 建新实体目录 → 老路径变联接
New-Item -ItemType Junction -Path $old -Target $stage | Out-Null
# 3) stage 改名为正式目录
Rename-Item $stage $new

Write-Host "完成：" -ForegroundColor Green
Write-Host ("  {0} → Junction → {1}" -f $old, (Get-Item $old -Force).Target)
Write-Host ("  {0} 真实目录，文件数 {1}" -f $new, (Get-ChildItem $new -Force | Measure-Object).Count)
Write-Host "`n记得跑一次 scripts\verify-migration.ps1 和 hubs 的 codesys 冒烟。" -ForegroundColor Cyan
