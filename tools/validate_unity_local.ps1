# Run Unity validation directly on the activated Windows desktop account.
param(
    [string]$Python = "$env:LOCALAPPDATA/Programs/Python/Python313/python.exe",
    [string]$Jdk = 'C:/Program Files/Java/jdk-23',
    [string]$PlayModeFilter,
    [ValidateSet('authenticated-ui', 'multiplayer')][string]$ResumeAt,
    [switch]$BuildOnly
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Unity validation requires Windows and an activated Unity Hub installation' }
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location $root
if (-not (Test-Path -LiteralPath $Python)) { throw 'Install Python 3.12/3.13 or supply -Python' }
if (-not (Test-Path -LiteralPath (Join-Path $Jdk 'bin/javac.exe'))) { throw 'Install JDK 23.0.2+7 or supply -Jdk' }
$pythonVersion = & $Python --version
if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3\.(12|13)\.') { throw 'Python 3.12 or 3.13 is required' }
$javaVersion = (& (Join-Path $Jdk 'bin/java.exe') -version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $javaVersion -notmatch '23\.0\.2\+7') { throw 'JDK 23.0.2+7 is required' }
$nodeVersion = & node --version
if ($LASTEXITCODE -ne 0 -or ($nodeVersion -notmatch '^v(\d+)\.' -or [int]$Matches[1] -lt 22)) { throw 'Node.js 22 or newer is required' }
$env:JAVA_HOME = $Jdk
$env:PYTHONPATH = "$root/Mtg_Projects;$root/Mtg_Projects/mtg_core"
$env:MANAFORGE_NETWORK_TIMING = '1'
$runRoot = Join-Path $root ('Artifacts/UnityLocal/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $runRoot | Out-Null
$evidenceId = Split-Path $runRoot -Leaf
$engine = Join-Path $runRoot 'engine'
$venv = Join-Path $runRoot 'venv'
& $Python -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the local validation environment' }
$env:PATH = "$venv/Scripts;$Jdk/bin;$env:PATH"
$commit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the source commit' }
$dirty = [bool](git status --porcelain --untracked-files=normal)
$reportPath = Join-Path $runRoot 'validation.json'
$report = [ordered]@{ schema = 1; commit = $commit; dirty = $dirty; status = 'running';
    started = [DateTime]::UtcNow.ToString('o'); stages = @() }
function Save-Report { $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8 }
$resumeReached = -not $ResumeAt
$resumeStage = if ($ResumeAt -eq 'authenticated-ui') { 'Packaged authenticated decision UI fixture' } else { 'Install standalone multiplayer relay' }
function Invoke-Stage([string]$Name, [scriptblock]$Action) {
    if ($ResumeAt -and -not $script:resumeReached) {
        if ($Name -eq $resumeStage) { $script:resumeReached = $true }
        elseif ($Name -notin @('Install local validation dependencies', 'Build Windows player', 'Prepare hash-pinned real engine')) {
            $report.stages += @{ name = $Name; status = 'skipped'; reason = 'Scoped acceptance continuation; consult earlier evidence for this stage' }
            Save-Report
            return
        }
    }
    Write-Output "=== $Name ==="
    $global:LASTEXITCODE = 0
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) { throw "Stage exited with code $LASTEXITCODE" }
        $report.stages += @{ name = $Name; status = 'passed' }
    } catch {
        $report.stages += @{ name = $Name; status = 'failed'; error = $_.Exception.Message }
        throw
    } finally { Save-Report }
}
Save-Report
Start-Transcript -Path (Join-Path $runRoot 'validation.log') | Out-Null
try {
    if ($BuildOnly) {
        if ($ResumeAt -or $PlayModeFilter) { throw 'BuildOnly cannot be combined with test or acceptance scopes' }
        $report.scope = 'build-only'
        $report.tests = 'skipped'
        Invoke-Stage 'Build Windows player' {
            $scenePath = Join-Path $root 'Mtg_Projects/mtg_play_unity/Assets/Manaforge/Scenes/Foundation.unity'
            $sceneBefore = [IO.File]::ReadAllBytes($scenePath)
            $settingsPath = Join-Path $root 'Mtg_Projects/mtg_play_unity/ProjectSettings/ProjectSettings.asset'
            $settingsBefore = [IO.File]::ReadAllBytes($settingsPath)
            try { ./tools/unity-play.ps1 -Mode Build }
            finally { [IO.File]::WriteAllBytes($scenePath, $sceneBefore); [IO.File]::WriteAllBytes($settingsPath, $settingsBefore) }
        }
        $report.status = 'built'
        return # Explicitly skips tests and never claims acceptance.
    }
    if ($ResumeAt -and $PlayModeFilter) { throw 'Choose either PlayModeFilter or ResumeAt' }
    if ($ResumeAt) { $report.scope = 'acceptance-continuation'; $report.resumedAt = $ResumeAt }
    if ($PlayModeFilter) {
        $report.scope = 'playmode-regression'
        $report.testFilter = $PlayModeFilter
        Invoke-Stage 'Focused PlayMode regression only' {
            ./tools/unity-play.ps1 -Mode PlayMode -Graphics -TestFilter $PlayModeFilter
        }
        $report.status = 'passed'
        return # Diagnostics only; never archive this as full player acceptance.
    }
    Invoke-Stage 'Install local validation dependencies' {
        python -m pip install -r requirements-dev.txt
        if ($LASTEXITCODE -ne 0) { throw 'Local validation dependencies failed' }
        python -m pip install -r Mtg_Projects/mtg_proxy/requirements.txt
    }
    Invoke-Stage 'Prepare deterministic scene' {
        # Preparation regenerates scene IDs; keep the caller's original source bytes.
        $scenePath = Join-Path $root 'Mtg_Projects/mtg_play_unity/Assets/Manaforge/Scenes/Foundation.unity'
        $sceneBefore = [IO.File]::ReadAllBytes($scenePath)
        try { ./tools/unity-play.ps1 -Mode Prepare }
        finally { [IO.File]::WriteAllBytes($scenePath, $sceneBefore) }
    }
    Invoke-Stage 'Focused EditMode tests' {
        ./tools/unity-play.ps1 -Mode EditMode -Graphics -DownloadGson
    }
    Invoke-Stage 'Focused PlayMode test' {
        ./tools/unity-play.ps1 -Mode PlayMode -Graphics
    }
    Invoke-Stage 'Build Windows player' {
        # Preparation regenerates scene IDs; keep the caller's original source bytes.
        $scenePath = Join-Path $root 'Mtg_Projects/mtg_play_unity/Assets/Manaforge/Scenes/Foundation.unity'
        $sceneBefore = [IO.File]::ReadAllBytes($scenePath)
        try { ./tools/unity-play.ps1 -Mode Build }
        finally { [IO.File]::WriteAllBytes($scenePath, $sceneBefore) }
    }
    Invoke-Stage 'Render packaged player smoke screenshot' {
        ./tools/unity-play.ps1 -Mode Smoke
    }
    Invoke-Stage 'Capture reusable forged-theme elements and default 1v1 fixture' {
        ./tools/capture_play_style.ps1
    }
    Invoke-Stage 'Prepare hash-pinned real engine' {
        python -m mtg_play.ci_prepare --destination "$engine" --jdk-path "$env:JAVA_HOME"
    }
    Invoke-Stage 'Packaged real-engine automatic payment without manual rescue' {
        foreach ($case in @('green', 'blue', 'generic', 'floating')) {
          python tools/check_play_unity_live.py --casting-case $case --payment-mode auto --no-capture --xmage-root "$engine" --jdk-path "$env:JAVA_HOME" --output "Mtg_Projects/mtg_play_unity/Artifacts/Payment-auto-$case/$evidenceId"
          if ($LASTEXITCODE -ne 0) { throw "Automatic payment failed: $case" }
        }
    }
    Invoke-Stage 'Packaged real-engine manual payment and full control' {
        foreach ($mode in @('manual', 'full-control')) {
          foreach ($case in @('green', 'floating')) {
            python tools/check_play_unity_live.py --casting-case $case --payment-mode $mode --no-capture --xmage-root "$engine" --jdk-path "$env:JAVA_HOME" --output "Mtg_Projects/mtg_play_unity/Artifacts/Payment-$mode-$case/$evidenceId"
            if ($LASTEXITCODE -ne 0) { throw "Manual payment failed: $mode $case" }
          }
        }
    }
    Invoke-Stage 'Real pile selection and destination evidence through the packaged player' {
        foreach ($choice in @('first', 'second')) {
          python tools/check_play_unity_live.py --casting-case pile --pile-choice $choice --payment-mode auto --no-capture --xmage-root "$engine" --jdk-path "$env:JAVA_HOME" --output "Mtg_Projects/mtg_play_unity/Artifacts/InGameChoice-pile-$choice/$evidenceId"
          if ($LASTEXITCODE -ne 0) { throw "Pile selection failed: $choice" }
        }
    }
    Invoke-Stage 'Real X and existing choice variants through the packaged player' {
        foreach ($case in @('x-zero', 'x', 'cancel', 'search', 'shared-roots', 'modes')) {
          python tools/check_play_unity_live.py --casting-case $case --payment-mode manual --no-capture --xmage-root "$engine" --jdk-path "$env:JAVA_HOME" --output "Mtg_Projects/mtg_play_unity/Artifacts/InGameChoice-$case/$evidenceId"
          if ($LASTEXITCODE -ne 0) { throw "In-game choice failed: $case" }
        }
    }
    Invoke-Stage 'Packaged desktop preview with public generated artwork' {
        python tools/check_play_deck_preview.py
    }
    Invoke-Stage 'Normal shuffled human versus AI match with automatic payment' {
        python tools/check_play_unity_game.py --public-decks --payment-mode auto --no-capture --xmage-root "$engine" --jdk-path "$env:JAVA_HOME" --output "Mtg_Projects/mtg_play_unity/Artifacts/Payment-normal-game/$evidenceId"
    }
    Invoke-Stage 'Confirmed concession through the live Escape menu' {
        python tools/check_play_unity_game.py --public-decks --concede --no-capture --xmage-root "$engine" --jdk-path "$env:JAVA_HOME" --output "Mtg_Projects/mtg_play_unity/Artifacts/Concede-menu/$evidenceId"
    }
    Invoke-Stage 'Packaged authenticated decision UI fixture' {
        python tools/check_play_unity_session.py --decisions
    }
    Invoke-Stage 'Install standalone multiplayer relay' {
        Push-Location multiplayer-relay
        try { npm.cmd ci --omit=dev --ignore-scripts; if ($LASTEXITCODE -ne 0) { throw 'Relay dependency installation failed' } } finally { Pop-Location }
    }
    Invoke-Stage 'Two Unity human seats through standalone relay' {
        $relayProcess = Start-Process -FilePath node -ArgumentList @('server.mjs') -WorkingDirectory multiplayer-relay -PassThru -WindowStyle Hidden
        try {
          $relayReady = $false
          for ($attempt = 0; $attempt -lt 50; $attempt++) {
            $probe = [Net.Sockets.TcpClient]::new()
            try {
              if ($probe.ConnectAsync('127.0.0.1', 8787).Wait(200) -and $probe.Connected) { $relayReady = $true; break }
            } catch { Start-Sleep -Milliseconds 100 } finally { $probe.Dispose() }
          }
          if (-not $relayReady) { throw 'Standalone relay did not start' }
          foreach ($format in @('freeform', 'commander')) {
            python tools/check_play_multiplayer.py --relay ws://127.0.0.1:8787 --format $format --xmage-root "$engine" --jdk-path "$env:JAVA_HOME" --output "Mtg_Projects/mtg_play_unity/Artifacts/Multiplayer/$format-$evidenceId.json"
            if ($LASTEXITCODE -ne 0) { throw "Two-Unity multiplayer failed for $format" }
          }
        } finally {
          if (-not $relayProcess.HasExited) { Stop-Process -Id $relayProcess.Id }
        }
    }
    $report.dirty = $dirty -or [bool](git status --porcelain --untracked-files=normal) -or ((git rev-parse HEAD).Trim() -ne $commit)
    $report.status = 'passed'
} catch {
    $report.status = 'failed'
    throw
} finally {
    $report.finished = [DateTime]::UtcNow.ToString('o')
    Save-Report
    Stop-Transcript | Out-Null
    Write-Output "Local Unity evidence: $reportPath"
}
if ($ResumeAt) { return } # Scoped evidence is never a full release acceptance archive.
if ($report.dirty) {
    Write-Output 'Local validation passed for a modified workspace. Commit changes and rerun before release packaging.'
} else {
    python tools/prepare_verified_unity_player.py --create $reportPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not archive the validated Unity player' }
}
