
$ErrorActionPreference = 'Continue'
# 本脚本位于 <项目根>\_tools\ 下，所以项目根 = $PSScriptRoot 的上一级。
# ⚠️ 之前把脚本挪进 _tools 却仍用 $PSScriptRoot 当项目根 → 去找 _tools\app\backend\app.py
#    （不存在）→ 服务永远起不来。这里显式解析，并做一次容错回退。
$ScriptDir = $PSScriptRoot
$Root = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $Root 'app\backend\app.py'))) { $Root = $ScriptDir }

function Get-PythonCandidates {
    $list = @()
    foreach ($name in @('py', 'python', 'python3')) {
        $c = Get-Command $name -ErrorAction SilentlyContinue
        if ($c) {
            if ($name -eq 'py') { $list += [pscustomobject]@{ Exe = $c.Source; Args = @('-3') } }
            else { $list += [pscustomobject]@{ Exe = $c.Source; Args = @() } }
        }
    }
    $roots = @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python*", "${env:ProgramFiles(x86)}\Python*")
    foreach ($r in $roots) {
        foreach ($exe in @(Get-ChildItem -Path (Join-Path $r 'python.exe') -ErrorAction SilentlyContinue)) {
            $list += [pscustomobject]@{ Exe = $exe.FullName; Args = @() }
        }
        foreach ($d in @(Get-ChildItem -Path $r -Directory -ErrorAction SilentlyContinue)) {
            $exe = Join-Path $d.FullName 'python.exe'
            if (Test-Path $exe) { $list += [pscustomobject]@{ Exe = $exe; Args = @() } }
        }
    }
    # 便携版自带 Python 时优先用它（2026-10-12：自带运行时就不用用户装 Python 了）
    $bundled = Join-Path $ScriptDir 'python\python.exe'
    if (Test-Path $bundled) { $list += [pscustomobject]@{ Exe = $bundled; Args = @() } }
    $dsh = 'C:\Users\win11_vmusers\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
    if (Test-Path $dsh) { $list += [pscustomobject]@{ Exe = $dsh; Args = @() } }
    return $list
}

function Test-PythonHasFlask($cand) {
    # 检查**核心依赖**是否齐（不只 flask）：缺 openai/docx 等会让组卷/判分脚本悄悄降级
    $all = @($cand.Args) + @('-c', 'import flask, openai, docx, openpyxl, requests, bs4')
    & $cand.Exe @all 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Select-WorkingPython {
    param([switch]$Quiet)
    $seen = @{}
    foreach ($c in Get-PythonCandidates) {
        if ($seen[$c.Exe]) { continue }
        $seen[$c.Exe] = $true
        if (Test-PythonHasFlask $c) {
            if (-not $Quiet) { Write-Host "  [找到] $($c.Exe)  (依赖已就绪)" -ForegroundColor Green }
            return $c
        } elseif (-not $Quiet) {
            Write-Host "  [跳过] $($c.Exe)  (依赖不全)" -ForegroundColor DarkGray
        }
    }
    return $null
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " 题库项目 - 启动中..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$py = Select-WorkingPython
if (-not $py) {
    Write-Host ""
    Write-Host "[提示] 没有找到『依赖齐全的 Python』，请先双击 安装依赖.bat" -ForegroundColor Yellow
    Write-Host "      （如果你还没装 Python，请到 https://www.python.org/downloads/ 安装，" -ForegroundColor Yellow
    Write-Host "        安装时务必勾选 Add Python to PATH）" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 1
}

# ① 先检查「是不是已经在跑」。
#    2026-10-24 事故复盘：旧进程占着 5000/5001 时，新进程因「端口全部被占用」立刻退出，
#    而下面的探测请求又被**旧服务**应答 → 页面显示"启动成功"，随后 Wait-Process 去等一个
#    已经死掉的 PID，报「找不到进程标识符为 4960 的进程」。所以先探测，再决定要不要启。
function Test-ServiceRunning([int]$port) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/quiz" -UseBasicParsing -TimeoutSec 1
        return ($r.StatusCode -eq 200 -and $r.Content -match '刷题')
    } catch { return $false }
}

for ($p = 5000; $p -le 5009; $p++) {
    if (Test-ServiceRunning $p) {
        Write-Host ""
        Write-Host "  [已在运行] 检测到服务：http://127.0.0.1:$p/quiz" -ForegroundColor Green
        Write-Host "  不会再启动第二个实例（否则会因端口被占而失败）。" -ForegroundColor DarkGray
        Write-Host "  ⚠️ 如果刚更新过代码却看不到效果：说明跑的还是**旧进程**。" -ForegroundColor Yellow
        Write-Host "     请先结束残留的 python.exe（任务管理器 / 或运行 _tools\stop.ps1），再重新启动。" -ForegroundColor Yellow
        Write-Host ""
        Start-Process "http://127.0.0.1:$p/quiz"
        Read-Host "按回车退出"
        exit 0
    }
}

# 端口文件先删掉，避免读到上次的旧值
$portFile = Join-Path $Root 'app\port.txt'
if (Test-Path $portFile) { Remove-Item $portFile -Force -ErrorAction SilentlyContinue }

# 把子进程的输出留档：服务要是启动即崩，这里能直接看到原因（例如端口全被占用）
$logDir = Join-Path $ScriptDir 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir 'server.log'
Remove-Item $logFile -Force -ErrorAction SilentlyContinue

Write-Host "正在启动服务（首次启动稍慢）..." -ForegroundColor Yellow
$appPath = Join-Path $Root 'app\backend\app.py'
$proc = Start-Process -FilePath $py.Exe -ArgumentList (@($py.Args) + @($appPath)) `
    -WorkingDirectory $Root -PassThru -NoNewWindow `
    -RedirectStandardOutput $logFile -RedirectStandardError ($logFile + '.err')

# 轮询：等服务真的起来，并从 port.txt 读**实际**端口（5000 被占时会回退到 5001）
$port = 5000
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path $portFile) {
        $t = (Get-Content $portFile -Raw -ErrorAction SilentlyContinue)
        if ($t) { $t = $t.Trim(); if ($t -match '^\d+$') { $port = [int]$t } }
    }
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/quiz" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    if ($proc.HasExited) { break }
}

if (-not $ok) {
    Write-Host ""
    Write-Host "[失败] 服务没能正常启动。" -ForegroundColor Red
    if ($proc.HasExited) {
        Write-Host "       原因：Python 进程已退出（退出码 $($proc.ExitCode)）。日志尾部：" -ForegroundColor Yellow
        foreach ($f in @($logFile + '.err', $logFile)) {
            if (Test-Path $f) {
                $tail = Get-Content -LiteralPath $f -Tail 12 -ErrorAction SilentlyContinue
                if ($tail) { $tail | ForEach-Object { Write-Host "       $_" -ForegroundColor DarkGray } }
            }
        }
        Write-Host "       （完整日志：$logFile）" -ForegroundColor DarkGray
    }
    Write-Host "       若是「端口全部被占用」：说明还有旧的服务进程在跑，先结束 python.exe 再启动。" -ForegroundColor Yellow
    Write-Host "       其它情况请先双击 安装依赖.bat，或在命令行手动运行：" -ForegroundColor Yellow
    Write-Host "       $($py.Exe) app\backend\app.py" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 1
}

$url = "http://127.0.0.1:$port/quiz"
Write-Host ""
Write-Host "  ✅ 启动成功！" -ForegroundColor Green
Write-Host "  刷题网址: $url" -ForegroundColor Green
Write-Host "  （已自动打开浏览器；若没弹出，请手动复制上面网址）" -ForegroundColor Gray
Write-Host ""
Write-Host "  ⚠️  不要关闭这个窗口，关掉它就等于停止服务。" -ForegroundColor Yellow
Write-Host "  停止服务：在本窗口按 Ctrl+C，或直接关闭窗口。" -ForegroundColor Gray
Write-Host ""
Start-Process $url

# 等子进程结束，并在退出时**顺手收尾**，避免再留下"看不见的 python 进程"占着端口。
# ⚠️ 不再用 `Wait-Process -Id $proc.Id`：进程若已退出，它会抛
#    「找不到进程标识符为 xxx 的进程」——用户看到的就是这句。
try {
    while (-not $proc.HasExited) { Start-Sleep -Milliseconds 800 }
} catch { }
finally {
    if ($proc -and -not $proc.HasExited) {
        try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch { }
    }
}
Write-Host "服务已停止。" -ForegroundColor Gray
Read-Host "按回车退出"
