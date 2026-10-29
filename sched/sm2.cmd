@echo off
chcp 65001 >nul
cd /d "C:\Users\win11_vmusers\Documents\deepseek-harness\default-workspace\????"
"C:\Users\win11_vmusers\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" "scripts\sm2_scheduler.py" --subject all >> "logs\cron.log" 2>&1
if errorlevel 1 echo [%date% %time%] sm2 exit=%errorlevel% >> "logs\cron_failures.log"
