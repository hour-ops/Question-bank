<#
.SYNOPSIS
  QuizBank project - Stage 10 scheduler installer (Windows Task Scheduler).

.DESCRIPTION
  This host has NO crontab; the `dsh-cron-scheduler` plugin was removed because the
  published package references a non-existent `dsh-cron` entry. Hence schtasks.

  SAFETY RULE (user requirement): scheduled jobs must be FREE of API spend.
    - fetch / parse / export / backup / update_progress / sm2 : zero API cost
    - validate_and_fill : only `--dry-run` (coverage report + cost estimate)
    - sync_outbox       : only `--dry-run` (queue depth report, NO judging)
    => PAID judging and question generation stay MANUAL.

  NOTE: schtasks tasks run only while the user is logged on (known limitation).
  NOTE: this script is ASCII-only on purpose - the active shell is Windows
        PowerShell 5.1, which reads UTF-8 files as ANSI and mangles non-ASCII.

  Usage:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_schtasks.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_schtasks.ps1 -Remove
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_schtasks.ps1 -List
#>
[CmdletBinding()]
param(
    [switch]$Remove,
    [switch]$List
)

$ErrorActionPreference = 'Stop'
$ROOT  = Split-Path -Parent $PSScriptRoot
$PY    = 'C:\Users\win11_vmusers\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$SCHED = Join-Path $ROOT 'sched'
$PREFIX = 'QuizBank'

$TASKS = @(
    @{ n='fetch';       s='scripts\fetch.py';                 a='--subject all'; sc='MINUTE'; mo=120;  st=$null;    d='crawl whitelisted sites (no API cost)' },
    @{ n='parse';       s='scripts\parse_inbox.py';           a='--subject all'; sc='MINUTE'; mo=240;  st=$null;    d='parse inbox into DB (only ingest entry, free)' },
    @{ n='coverage';    s='scripts\validate_and_fill.py';     a='--dry-run';     sc='DAILY';  mo=$null; st='03:00'; d='coverage report + cost estimate (dry-run only)' },
    @{ n='export';      s='scripts\export_papers.py';         a='--subject all'; sc='DAILY';  mo=$null; st='03:30'; d='export papers docx/pdf/xlsx/apkg (free)' },
    @{ n='sync-report'; s='scripts\sync_outbox.py';           a='--dry-run';     sc='MINUTE'; mo=10;    st=$null;    d='judge queue depth report (dry-run only, NO judging)' },
    @{ n='progress';    s='scripts\update_daily_progress.py'; a='';              sc='HOURLY'; mo=$null; st='00:05'; d='daily progress aggregation (free)' },
    @{ n='sm2';         s='scripts\sm2_scheduler.py';         a='--subject all'; sc='HOURLY'; mo=$null; st='00:15'; d='SM-2 scheduling (free, offset 15 min)' },
    @{ n='backup';      s='scripts\backup.py';                a='--keep 7';      sc='WEEKLY'; mo=$null; st='04:00'; d='consistent snapshot + log rotation (Sunday)'; dow='SUN' }
)

function Get-TaskName($t) { "$PREFIX\$($t.n)" }

if ($List) {
    $q = schtasks /query /fo CSV /nh 2>$null | Where-Object { $_ -like "*$PREFIX*" }
    Write-Host ("registered tasks: " + (($q | Measure-Object).Count))
    $q | ForEach-Object { Write-Host ("  " + ($_ -split ',')[0].Trim('"')) }
    return
}

if ($Remove) {
    foreach ($t in $TASKS) {
        $tn = Get-TaskName $t
        schtasks /delete /tn $tn /f 2>$null | Out-Null
        Write-Host "  deleted $tn"
    }
    Write-Host "done: $PREFIX tasks removed"
    return
}

New-Item -ItemType Directory -Force -Path $SCHED | Out-Null

# 1) write .cmd wrappers as pure ASCII (a BOM would break cmd.exe)
foreach ($t in $TASKS) {
    $cmdPath = Join-Path $SCHED "$($t.n).cmd"
    $lines = @(
        '@echo off',
        'chcp 65001 >nul',
        "cd /d `"$ROOT`"",
        "`"$PY`" `"$($t.s)`" $($t.a) >> `"logs\cron.log`" 2>&1",
        "if errorlevel 1 echo [%date% %time%] $($t.n) exit=%errorlevel% >> `"logs\cron_failures.log`""
    )
    Set-Content -Path $cmdPath -Value $lines -Encoding ascii
    Write-Host "  wrote $cmdPath"
}

# 2) register tasks (idempotent: /f overwrites)
foreach ($t in $TASKS) {
    $tn = Get-TaskName $t
    $tr = "`"$(Join-Path $SCHED "$($t.n).cmd")`""
    $argv = @('/create', '/tn', $tn, '/tr', $tr, '/sc', $t.sc, '/f')
    if ($t.mo)  { $argv += @('/mo', "$($t.mo)") }
    if ($t.st)  { $argv += @('/st', $t.st) }
    if ($t.dow) { $argv += @('/d', $t.dow) }
    $out = & schtasks @argv 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host "  [ok]   $tn  ($($t.sc) $($t.mo)$($t.st))  - $($t.d)" }
    else { Write-Host "  [FAIL] $tn  exit=$LASTEXITCODE :: $out" }
}

Write-Host ""
Write-Host "=== verify ==="
$q = schtasks /query /fo CSV /nh 2>$null | Where-Object { $_ -like "*$PREFIX*" }
Write-Host ("registered: " + (($q | Measure-Object).Count) + " / expected " + $TASKS.Count)
$q | ForEach-Object { Write-Host ("  " + ($_ -split ',')[0].Trim('"')) }
