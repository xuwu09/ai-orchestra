@echo off
rem ============================================================
rem  ChatParty launcher TEMPLATE (idempotent + CDP check)
rem  1) EDIT the exe path below to your own ChatParty install
rem  2) CDP 9222 is required by tools\chatparty\* scripts
rem     (login watchdog / trial_send / cdp_inspect / bridge)
rem  Behavior:
rem   - ChatParty not running      -> launch with CDP 9222
rem   - running, CDP listening     -> do nothing (idempotent)
rem   - running, no CDP 9222       -> warn (you double-clicked
rem     the exe directly; official exe has no built-in CDP.
rem     Close ChatParty, then run this launcher again)
rem ============================================================
tasklist /FI "IMAGENAME eq ChatParty.exe" 2>nul | find /I "ChatParty.exe" >nul
if %errorlevel%==0 goto running
start "" "D:\Path\To\ChatParty\ChatParty.exe" --remote-debugging-port=9222
exit /b 0
:running
netstat -ano 2>nul | find /I ":9222" | find /I "LISTENING" >nul
if %errorlevel%==0 exit /b 0
echo [ChatParty] already running but WITHOUT CDP 9222.
echo Maybe you double-clicked the exe directly. Close ChatParty, then run this launcher again.
exit /b 1
