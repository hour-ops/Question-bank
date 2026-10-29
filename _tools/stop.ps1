# 停止「题库项目」服务：结束所有命令行里带 app\backend\app.py 的 python 进程。
# 为什么需要：启动脚本用 Start-Process 起的 python 是独立进程，**关掉启动窗口不会结束它**，
# 于是残留进程会一直占着 5000/5001……下次启动就可能「端口全被占用」而失败。
$ErrorActionPreference = 'Continue'

$ScriptDir = $PSScriptRoot
$Root = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $Root 'app\backend\app.py'))) { $Root = $ScriptDir }
$target = (Join-Path $Root 'app\backend\app.py')

Write-Host "正在查找本项目的服务进程…" -ForegroundColor Cyan

$found = @()
foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue)) {
    if ($p.CommandLine -and $p.CommandLine -like "*app\backend\app.py*") {
        $found += $p
    }
}

if (-not $found) {
    Write-Host "没有发现正在运行的服务进程。" -ForegroundColor Green
    Read-Host "按回车退出"
    exit 0
}

foreach ($p in $found) {
    Write-Host ("  结束 PID {0}  {1}" -f $p.ProcessId, $p.CommandLine) -ForegroundColor Yellow
    try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop }
    catch { Write-Host ("    失败：{0}" -f $_.Exception.Message) -ForegroundColor Red }
}

Start-Sleep -Milliseconds 500
$left = @()
foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue)) {
    if ($p.CommandLine -and $p.CommandLine -like "*app\backend\app.py*") { $left += $p.ProcessId }
}
if ($left) {
    Write-Host ("仍有进程未结束：{0}（可能不是本用户启动，需管理员权限）" -f ($left -join ', ')) -ForegroundColor Red
} else {
    Write-Host "全部已结束，可以重新双击 启动.bat。" -ForegroundColor Green
}
Read-Host "按回车退出"
