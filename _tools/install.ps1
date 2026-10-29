# 题库项目 · 安装依赖（重写版，2026-10-30）
#
# 为什么重写：老脚本用 `& $exe @($args)` 当 splatting，PowerShell 会把整个数组当成
# 一个参数；再加上它把 PATH 里的 32 位 Python 排在前面，而 _tools\wheels 里全是
# win_amd64 的编译型 wheel（lxml / Pillow / pydantic_core …），结果必挂在
#   ERROR: No matching distribution found for lxml==6.1.3
# 新脚本：① 只认 64 位解释器（按优先级探测）；② 正确的 splatting 写法；
#         ③ 失败时给出可执行的下一步。
#
# 自测开关：设置环境变量 TK_DRYRUN=1 时只打印命令、不真正执行（不会改动环境）。

$ErrorActionPreference = 'Continue'
$ScriptDir = $PSScriptRoot
$Root = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $Root 'app\backend\app.py'))) { $Root = $ScriptDir }

$WheelDir = Join-Path $ScriptDir 'wheels'
$CoreReq  = Join-Path $Root 'requirements-core.txt'
$OldReq   = Join-Path $Root 'requirements.txt'
$Mirrors  = @(
    'https://pypi.tuna.tsinghua.edu.cn/simple',
    'https://mirrors.aliyun.com/pypi/simple',
    'https://mirrors.cloud.tencent.com/pypi/simple'
)
$DryRun = ($env:TK_DRYRUN -eq '1')

function Invoke-Py {
    param($Exe, [string[]]$PyArgs)
    if ($DryRun) {
        Write-Host ("  [dry-run] " + $Exe + " " + ($PyArgs -join ' ')) -ForegroundColor DarkGray
        return 0
    }
    & $Exe @PyArgs
    return $LASTEXITCODE
}

function Test-Deps($Exe) {
    return ((Invoke-Py $Exe @('-c', 'import flask, openai, docx, openpyxl, requests, bs4')) -eq 0)
}

function Get-Bits($Exe) {
    if ($DryRun) { return 64 }
    $out = & $Exe '-c' 'import sys;print(64 if sys.maxsize > 2**32 else 32)' 2>$null
    try { return [int](("$out").Trim()) } catch { return 0 }
}

function Get-PyVersion($Exe) {
    if ($DryRun) { return '3.12' }
    $out = & $Exe '-c' 'import sys;print("%d.%d" % sys.version_info[:2])' 2>$null
    return ("$out").Trim()
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " 题库项目 - 安装依赖（只需运行一次）" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ---------------------------------------------------------------- 候选解释器（64 位优先）
$cands = New-Object System.Collections.ArrayList
$bundled = Join-Path $ScriptDir 'python\python.exe'
if (Test-Path $bundled) { [void]$cands.Add($bundled) }
$dshPy = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
if (Test-Path $dshPy) { [void]$cands.Add($dshPy) }
$pyLauncher = (Get-Command py -ErrorAction SilentlyContinue)
if ($pyLauncher -and $pyLauncher.Source) {
    foreach ($ver in @('-3.12-64', '-3-64')) {
        $path64 = (& $pyLauncher.Source $ver '-c' 'import sys;print(sys.executable)' 2>$null)
        $path64 = ("$path64").Trim()
        if ($path64 -and (Test-Path $path64)) { [void]$cands.Add($path64) }
    }
}
foreach ($name in @('python', 'python3')) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c -and $c.Source) { [void]$cands.Add($c.Source) }
}
foreach ($base in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles", "${env:ProgramFiles(x86)}")) {
    if (-not $base -or -not (Test-Path $base)) { continue }
    foreach ($d in @(Get-ChildItem -Path $base -Directory -Filter 'Python*' -ErrorAction SilentlyContinue)) {
        $exe = Join-Path $d.FullName 'python.exe'
        if (Test-Path $exe) { [void]$cands.Add($exe) }
    }
}

# 去重 + 分 64/32 位
$seen = @{}
$py64 = @()
$py32 = @()
foreach ($exe in $cands) {
    if (-not $exe -or $seen[$exe]) { continue }
    $seen[$exe] = $true
    if ((Get-Bits $exe) -eq 64) { $py64 += $exe } else { $py32 += $exe }
}

$pyExe = $null
foreach ($exe in $py64) { if (Test-Deps $exe) { $pyExe = $exe; break } }
if (-not $pyExe -and $py64.Count -gt 0) { $pyExe = $py64[0] }
$SkipWheels = $false
if (-not $pyExe) {
    if ($py32.Count -gt 0) {
        $pyExe = $py32[0]
        $SkipWheels = $true
        Write-Host ""
        Write-Host "[警告] 只找到 32 位 Python：$pyExe" -ForegroundColor Yellow
        Write-Host "       _tools\wheels 里的编译型包是 win_amd64，32 位装不上，已改成联网安装。" -ForegroundColor Yellow
        Write-Host "       推荐装 64 位 Python 3.12 后重跑（更快且可离线）：" -ForegroundColor Yellow
        Write-Host "       https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    } else {
        Write-Host "[错误] 没找到任何 Python。" -ForegroundColor Red
        Write-Host "       请安装 64 位 Python 3.12（勾选 Add Python to PATH）后重跑：" -ForegroundColor Yellow
        Write-Host "       https://www.python.org/downloads/windows/" -ForegroundColor Yellow
        Start-Process "https://www.python.org/downloads/windows/"
        Read-Host "按回车退出"
        exit 1
    }
}

Write-Host ""
Write-Host "使用解释器: $pyExe" -ForegroundColor Green
Write-Host "Python 版本: $(Get-PyVersion $pyExe)  ($(Get-Bits $pyExe)-bit)" -ForegroundColor DarkGray
$req = if (Test-Path $CoreReq) { $CoreReq } else { $OldReq }
Write-Host "依赖清单: $req" -ForegroundColor DarkGray

$ok = $false
# ---------------------------------------------------------------- ① 离线 wheel
if ((-not $SkipWheels) -and (Test-Path $WheelDir)) {
    $n = @(Get-ChildItem -Path (Join-Path $WheelDir '*.whl') -ErrorAction SilentlyContinue).Count
    if ($n -gt 0) {
        Write-Host ""
        Write-Host "[1/2] 离线安装（$n 个 wheel，不联网）..." -ForegroundColor Yellow
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $code = Invoke-Py $pyExe @('-m', 'pip', 'install', '-r', $req, '--no-index',
                                   '--find-links', $WheelDir, '--no-cache-dir', '--disable-pip-version-check')
        $sw.Stop()
        if ($code -eq 0) {
            $ok = $true
            Write-Host ("[完成] 离线安装成功，用时 {0:N1} 秒" -f $sw.Elapsed.TotalSeconds) -ForegroundColor Green
        } else {
            Write-Host ("[提示] 离线安装失败（{0:N1} 秒），改用国内镜像。" -f $sw.Elapsed.TotalSeconds) -ForegroundColor Yellow
        }
    }
} elseif ($SkipWheels) {
    Write-Host ""
    Write-Host "[1/2] 跳过离线 wheel（32 位 Python 与 amd64 wheel 不匹配）" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- ② 镜像兜底
if (-not $ok) {
    Write-Host ""
    Write-Host "[2/2] 从国内镜像安装（自动轮询）..." -ForegroundColor Yellow
    foreach ($m in $Mirrors) {
        Write-Host "  镜像: $m" -ForegroundColor DarkGray
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $code = Invoke-Py $pyExe @('-m', 'pip', 'install', '-r', $req, '-i', $m,
                                   '--only-binary', ':all:', '--no-cache-dir', '--disable-pip-version-check')
        $sw.Stop()
        if ($code -eq 0) {
            $ok = $true
            Write-Host ("[完成] 用时 {0:N1} 秒" -f $sw.Elapsed.TotalSeconds) -ForegroundColor Green
            break
        }
        Write-Host "  该镜像失败，换下一个" -ForegroundColor Yellow
    }
}

if (-not $ok) {
    Write-Host ""
    Write-Host "[失败] 依赖没装完。常见原因：" -ForegroundColor Red
    Write-Host "  1) Python 是 32 位 —— 换 64 位 Python 3.12 再跑一次；" -ForegroundColor Yellow
    Write-Host "  2) 网络不通 —— 挂代理，或分步装 requirements-parsing.txt；" -ForegroundColor Yellow
    Write-Host "  3) 版本冲突 —— 先 pip uninstall 冲突包再重试。" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 1
}

Write-Host ""
Write-Host "自检：" -ForegroundColor Cyan
$check = Invoke-Py $pyExe @('-c', 'import flask, openai, requests, bs4, docx, openpyxl, reportlab, genanki; print("核心依赖齐了")')
if ($check -ne 0) {
    Write-Host "[警告] 核心依赖自检没通过（上面有报错）。" -ForegroundColor Red
} else {
    Write-Host "核心依赖齐了 ✓" -ForegroundColor Green
}
Write-Host ""
Write-Host "[完成] 现在可以双击 启动.bat" -ForegroundColor Green
Write-Host "       要导入 PDF 素材时再执行：pip install -r requirements-parsing.txt" -ForegroundColor DarkGray
if (-not $DryRun) { Read-Host "按回车退出" }
