# One-click setup and run of the rtlgym local-model experiment on Windows.
# Started by RUN_ME.bat. Safe to run again: finished steps are skipped.
#   1. Installs WSL (Windows asks for admin approval; a restart may be needed).
#   2. Installs Ubuntu 24.04. Its disk goes to $env:RTLGYM_WSL_DIR, or by default to
#      <drive of this repo>:\Program_Files\WSL.
#   3. On Windows 11 22H2+, lets Ubuntu reach Ollama on localhost (mirrored
#      networking), merged into an existing .wslconfig with a backup.
#   4. Installs the EDA tools (as root), then rtlgym and its tests as a normal user.
#   5. Starts Ollama if needed and runs the experiment (see run_eval.sh).
# Optional settings (environment variables, read by run_eval.sh): MODELS, THINK,
# MAX_TOKENS, TIMEOUT, SAMPLES, TURNS, PAIRED, SEED, and RTLGYM_WSL_DIR.
param([string]$Settings = "")   # set by the admin relaunch below; not for direct use

$SettingNames = "MODELS", "THINK", "MAX_TOKENS", "TIMEOUT", "SAMPLES", "TURNS", "PAIRED",
                "SEED", "RTLGYM_WSL_DIR"
# An elevated process started with -Verb RunAs does not inherit this console's
# environment, so the settings travel as an argument (base64 JSON) instead.
if ($Settings) {
    $json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Settings))
    ($json | ConvertFrom-Json).PSObject.Properties | ForEach-Object {
        [Environment]::SetEnvironmentVariable($_.Name, [string]$_.Value)
    }
}

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = (Resolve-Path (Join-Path $Here "..\..")).Path
$Distro = "Ubuntu-24.04"
$WslDir = $env:RTLGYM_WSL_DIR
if (-not $WslDir) { $WslDir = (Split-Path -Qualifier $Repo) + "\Program_Files\WSL" }
$Target = Join-Path $WslDir $Distro
$env:WSL_UTF8 = "1"

function Stop-Here([string]$msg) {
    Write-Host ""
    Write-Host $msg -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

function ConvertTo-WslPath([string]$p) {
    $drive = $p.Substring(0, 1).ToLower()
    return "/mnt/$drive" + $p.Substring(2).Replace("\", "/")
}

function Test-NeedsRestart([string]$text) {
    # Messages WSL prints when Windows must restart to finish installing.
    return $text -match ("(?i)reboot|restart (your|the) (computer|system|machine|pc)|" +
                         "0x80370102|enable the Virtual Machine Platform")
}

# Admin rights are needed to install WSL; relaunch elevated (Windows shows a prompt).
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $carry = @{}
    foreach ($v in $SettingNames) {
        $val = [Environment]::GetEnvironmentVariable($v)
        if ($val) { $carry[$v] = $val }
    }
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
        (ConvertTo-Json $carry -Compress)))
    Start-Process powershell -Verb RunAs -ArgumentList (
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Settings $b64")
    exit 0
}

# Keep Windows from sleeping while this window runs. This does NOT stop sleep when a
# laptop lid is closed, and it does not change any power settings.
Add-Type -Namespace RtlGym -Name Power -MemberDefinition `
    '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
[RtlGym.Power]::SetThreadExecutionState([uint32]2147483649) | Out-Null  # continuous + system

Write-Host "Settings for this run:"
foreach ($v in $SettingNames) {
    $val = [Environment]::GetEnvironmentVariable($v)
    if (-not $val) { $val = "(default)" }
    Write-Host ("  {0,-15} {1}" -f $v, $val)
}

$build = [Environment]::OSVersion.Version.Build
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$cFree = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
Write-Host "Windows build $build | RAM $ramGB GB | free on C: $cFree GB | repo $Repo"
Write-Host "Keep the laptop plugged in with the lid open: closing the lid may still sleep it."

# 1. WSL itself (a Windows component; it always lives on C:, a few hundred MB).
Write-Host "`n[1/5] WSL"
$status = (wsl.exe --status 2>&1 | Out-String)
wsl.exe --version *> $null
if ($LASTEXITCODE -ne 0) {
    $out = (wsl.exe --install --no-distribution 2>&1 | Out-String)
    Write-Host $out
    Stop-Here "WSL was installed. Restart Windows, then run RUN_ME.bat again to continue."
}
if (Test-NeedsRestart $status) {
    Write-Host $status
    Stop-Here "WSL needs a Windows restart to finish installing. Restart, then run again."
}
# Updating WSL can take a while; never let it hang the whole run.
$upd = Start-Process wsl.exe -ArgumentList "--update" -PassThru -WindowStyle Hidden
if (-not $upd.WaitForExit(600000)) {
    $upd.Kill()
    Write-Host "  'wsl --update' took over 10 minutes; skipped" -ForegroundColor Yellow
}

# 2. Ubuntu.
Write-Host "[2/5] Ubuntu ($Target)"
$installed = (wsl.exe --list --quiet) -join "`n"
if ($installed -notmatch [regex]::Escape($Distro)) {
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    $out = (wsl.exe --install -d $Distro --location $Target --no-launch 2>&1 | Out-String)
    Write-Host $out
    if (Test-NeedsRestart $out) {
        Stop-Here "Windows must restart before Ubuntu can be installed. Restart, then run again."
    }
    if ($LASTEXITCODE -ne 0) { Stop-Here "Ubuntu install failed (exit code $LASTEXITCODE)." }
} else {
    Write-Host "  already installed"
}

# 3. Networking: mirrored mode needs Windows 11 22H2 (build 22621) or later.
Write-Host "[3/5] Networking"
$cfg = Join-Path $env:USERPROFILE ".wslconfig"
if ($build -lt 22621) {
    Write-Host "  Windows build $build is older than 11 22H2: mirrored networking is not" `
        "available. Ubuntu will try the Windows host address; Ollama must then listen on" `
        "it (set OLLAMA_HOST=0.0.0.0 for Ollama and allow it through the firewall)." `
        -ForegroundColor Yellow
} else {
    # Keep the file's own encoding (UTF-8 without a BOM if new or unmarked).
    $text = ""
    $enc = New-Object Text.UTF8Encoding($false)
    if (Test-Path $cfg) {
        $reader = New-Object IO.StreamReader($cfg, $enc, $true)
        $text = $reader.ReadToEnd()
        $enc = $reader.CurrentEncoding
        $reader.Close()
    }
    if ($text -match "(?im)^\s*networkingMode\s*=") {
        Write-Host "  .wslconfig already sets networkingMode; left unchanged"
    } else {
        if (Test-Path $cfg) {
            $bak = "$cfg.bak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
            Copy-Item $cfg $bak
            Write-Host "  backup: $bak"
        }
        if ($text -match "(?im)^[ \t]*\[wsl2\][ \t]*\r?$") {
            $text = [regex]::Replace($text, "(?im)^[ \t]*\[wsl2\][ \t]*(\r?)$",
            ('[wsl2]$1' + "`n" + 'networkingMode=mirrored$1'), 1)
        } else {
            $text = ($text.TrimEnd() + "`r`n`r`n[wsl2]`r`nnetworkingMode=mirrored").Trim()
        }
        [IO.File]::WriteAllText($cfg, $text, $enc)
        Write-Host "  added networkingMode=mirrored to $cfg"
        # The change applies once WSL restarts. Restarting stops EVERY running distro
        # (Docker Desktop included), so ask first if any are running.
        $running = (wsl.exe --list --running --quiet 2>$null | Out-String).Trim()
        if ($running) {
            Write-Host "  WSL must restart for this to take effect. Running now:" `
                ($running -replace "\s+", ", ") -ForegroundColor Yellow
            Write-Host "  Restarting stops all of them, including Docker Desktop if it uses WSL."
            $ans = Read-Host "  Restart WSL now? [y/N]"
            if ($ans -notmatch "^[yY]") {
                Stop-Here ("Not restarted. Run 'wsl --shutdown' when convenient, " +
                           "then run RUN_ME.bat again.")
            }
            wsl.exe --shutdown
        }
    }
}

# 4. Tools as root (system packages); rtlgym as a normal user.
Write-Host "[4/5] Tools and rtlgym"
$User = (wsl.exe -d $Distro -- whoami 2>$null | Out-String).Trim()
if (-not $User -or $User -eq "root") {
    $User = "rtlgym"   # an unprivileged account with no password and no sudo
    wsl.exe -d $Distro -u root -- sh -c "id -u $User >/dev/null 2>&1 || useradd -m -s /bin/bash $User"
}
Write-Host "  Linux user: $User"
$LinuxHere = ConvertTo-WslPath $Here
$LinuxRepo = ConvertTo-WslPath $Repo
wsl.exe -d $Distro -u root -- bash "$LinuxHere/setup_system.sh"
if ($LASTEXITCODE -ne 0) { Stop-Here "Installing the EDA tools failed; see above." }
wsl.exe -d $Distro -u $User -- env REPO_SRC="$LinuxRepo" bash "$LinuxHere/setup_user.sh"
if ($LASTEXITCODE -ne 0) { Stop-Here "Setting up rtlgym failed; see above." }

# 5. Ollama on Windows, then the experiment.
Write-Host "[5/5] Ollama and the experiment"
function Test-Ollama {
    try { Invoke-RestMethod -TimeoutSec 3 http://localhost:11434/api/tags | Out-Null; $true }
    catch { $false }
}
if (-not (Test-Ollama)) {
    $app = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
    if (Test-Path $app) { Start-Process $app }
    else { Start-Process ollama -ArgumentList "serve" -WindowStyle Minimized }
    for ($i = 0; $i -lt 30 -and -not (Test-Ollama); $i++) { Start-Sleep -Seconds 2 }
    if (-not (Test-Ollama)) { Stop-Here "Ollama is not running. Start the Ollama app, then rerun." }
}
$pass = @()
foreach ($v in "MODELS", "THINK", "MAX_TOKENS", "TIMEOUT", "SAMPLES", "TURNS", "PAIRED", "SEED") {
    $val = [Environment]::GetEnvironmentVariable($v)
    if ($val) { $pass += "$v=$val" }
}
Write-Host "Started $(Get-Date -Format 'HH:mm'). Keep this window open; it may take hours."
wsl.exe -d $Distro -u $User -- env REPO_SRC="$LinuxRepo" @pass bash "$LinuxHere/run_eval.sh" all
Write-Host "`nFinished $(Get-Date -Format 'HH:mm'). Results: $Repo\results\local"
Read-Host "Press Enter to close"
