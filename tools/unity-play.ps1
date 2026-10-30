param(
    [ValidateSet('Prepare', 'EditMode', 'PlayMode', 'Build', 'Smoke', 'ArtworkSmoke')]
    [string]$Mode = 'Prepare',
    [string]$EditorPath = $env:MANAFORGE_UNITY_EDITOR,
    [int]$TimeoutSeconds = 1200,
    [string]$FixtureDirectory,
    [ValidateSet(20, 70, 200)]
    [int]$FixtureCount = 20,
    [switch]$Benchmark,
    [switch]$DownloadGson
)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../Mtg_Projects/mtg_play_unity'))
$artifacts = Join-Path $project 'Artifacts'
New-Item -ItemType Directory -Force $artifacts | Out-Null
$version = (Get-Content (Join-Path $project 'ProjectSettings/ProjectVersion.txt') | Select-String '^m_EditorVersion: ').ToString().Split(' ')[1]
if (-not $EditorPath) { $EditorPath = "C:/Program Files/Unity/Hub/Editor/$version/Editor/Unity.exe" }

function Invoke-OwnedProcess([string]$Executable, [string[]]$Arguments) {
    # Every path argument is quoted; no shell command is built or evaluated.
    $quoted = $Arguments | ForEach-Object {
        if ($_ -match '"') { throw 'Embedded quotes are not supported in arguments' }
        '"' + $_ + '"'
    }
    $process = Start-Process -FilePath $Executable -ArgumentList $quoted -PassThru -WindowStyle Hidden
    $elapsed = [Diagnostics.Stopwatch]::StartNew()
    $peakWorking = [long]0
    $peakPrivate = [long]0
    while (-not $process.WaitForExit(50)) {
        if ($Mode -eq 'ArtworkSmoke' -and $Benchmark) {
            try {
                $process.Refresh()
                if (-not $process.HasExited) {
                    $peakWorking = [Math]::Max($peakWorking, $process.WorkingSet64)
                    $peakPrivate = [Math]::Max($peakPrivate, $process.PrivateMemorySize64)
                }
            } catch {
                if (-not $process.HasExited) { throw }
            }
        }
        if ($elapsed.Elapsed.TotalSeconds -ge $TimeoutSeconds) { break }
    }
    if (-not $process.HasExited) {
        $process.Kill($true)
        $process.WaitForExit()
        throw "Owned $Mode process exceeded timeout"
    }
    if ($process.ExitCode -ne 0) { throw "$Mode process failed with exit code $($process.ExitCode); inspect Artifacts" }
    if ($Mode -eq 'ArtworkSmoke') {
        $log = Join-Path $artifacts "artwork-$FixtureCount.log"
        if (Select-String -LiteralPath $log -Pattern '^[A-Za-z][A-Za-z0-9.]*Exception:' -Quiet) { throw 'Artwork player logged an exception' }
    }
    if ($Mode -eq 'ArtworkSmoke' -and $Benchmark) {
        [ordered]@{ reportVersion = 1; peakWorkingSetBytes = $peakWorking; peakPrivateBytes = $peakPrivate;
            processElapsedMs = $elapsed.Elapsed.TotalMilliseconds;
            method = 'owned Windows process sampled every 50 ms from launch through exit; includes screenshot readback' } |
            ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $output "process-$FixtureCount.json")
    }
}

if ($Mode -eq 'ArtworkSmoke') {
    if (-not $FixtureDirectory) { throw 'ArtworkSmoke requires an existing offline fixture directory' }
    $fixture = (Resolve-Path -LiteralPath $FixtureDirectory).Path
    $output = Join-Path $artifacts $(if ($Benchmark) { 'ArtworkBenchmark' } else { 'ArtworkScene' })
    New-Item -ItemType Directory -Force $output | Out-Null
    if ($Benchmark) {
        $priorProcess = Join-Path $output "process-$FixtureCount.json"
        if (Test-Path -LiteralPath $priorProcess) { Remove-Item -LiteralPath $priorProcess }
    }
    foreach ($extension in @('json', 'png')) {
        $prior = Join-Path $output "artwork-$FixtureCount.$extension"
        if (Test-Path -LiteralPath $prior) { Remove-Item -LiteralPath $prior }
    }
    Invoke-OwnedProcess (Join-Path $project 'Builds/Windows/ManaforgePlay.exe') @(
        '-screen-fullscreen', '0', '-screen-width', '1280', '-screen-height', '720',
        '-logFile', (Join-Path $artifacts "artwork-$FixtureCount.log"),
        '-manaforgeArtworkFixture', $fixture, '-manaforgeArtworkOutput', $output,
        '-manaforgeFixtureCount', "$FixtureCount", '-manaforgeArtworkBenchmark', $(if ($Benchmark) { '1' } else { '0' })
    )
    $report = Get-Content (Join-Path $output "artwork-$FixtureCount.json") -Raw | ConvertFrom-Json
    $image = Get-Item (Join-Path $output "artwork-$FixtureCount.png")
    if (-not $report.fixtureOnly -or $report.objectCount -ne $FixtureCount -or
        $report.textureCount -lt 1 -or $report.textureBytes -gt 67108864 -or
        $report.editorVersion -ne $version -or $image.Length -lt 1000) { throw 'Artwork smoke failed' }
    if ($Benchmark -and (-not $report.measurementComplete -or $report.frames.sampleCount -lt 240 -or
        $report.selectionCount -lt 2 -or $report.tapCount -lt 1 -or $report.targetCount -lt 1 -or
        $report.processToReadyMs -le 0)) { throw 'Incomplete artwork benchmark' }
    if ($Benchmark) {
        $memory = Get-Content (Join-Path $output "process-$FixtureCount.json") -Raw | ConvertFrom-Json
        if ($memory.peakWorkingSetBytes -le 0 -or $memory.peakPrivateBytes -le 0) { throw 'Missing process memory evidence' }
        Write-Output ($memory | ConvertTo-Json)
    }
    # Raw samples stay in the artifact; keep console output bounded.
    foreach ($name in @('intervalsMs', 'gpuIntervalsMs', 'cpuIntervalsMs')) { $report.PSObject.Properties.Remove($name) }
    Write-Output ($report | ConvertTo-Json -Depth 5)
    exit 0
}

if ($Mode -eq 'Smoke') {
    $output = Join-Path $artifacts 'PlayerSmoke'
    New-Item -ItemType Directory -Force $output | Out-Null
    # Remove only prior known reports: stale evidence must never pass a new run.
    foreach ($name in @('smoke.json', 'foundation.png')) {
        $prior = Join-Path $output $name
        if (Test-Path -LiteralPath $prior) { Remove-Item -LiteralPath $prior }
    }
    Invoke-OwnedProcess (Join-Path $project 'Builds/Windows/ManaforgePlay.exe') @(
        '-screen-fullscreen', '0', '-screen-width', '1280', '-screen-height', '720',
        '-logFile', (Join-Path $artifacts 'player.log'), '-manaforgeSmokeOutput', $output
    )
    $report = Get-Content (Join-Path $output 'smoke.json') -Raw | ConvertFrom-Json
    if (-not $report.passed -or $report.editorVersion -ne $version) { throw 'Player smoke failed' }
    Write-Output ($report | ConvertTo-Json)
    exit 0
}
if (-not (Test-Path -LiteralPath $EditorPath)) { throw "Pinned Unity editor missing: $EditorPath" }
$installed = (Get-Item -LiteralPath $EditorPath).VersionInfo.ProductVersion
if (-not $installed.StartsWith($version)) { throw "Editor version mismatch: expected $version, found $installed" }
if ($Mode -eq 'EditMode') {
    # Build a current test-only Java peer; Python does not relay any gameplay frames.
    $dummyArguments = @((Join-Path $PSScriptRoot 'check_play_java_protocol.py'), '--dummy-output', (Join-Path $artifacts 'JavaDummy'))
    $cachedGson = Join-Path $artifacts 'JavaDummy/gson.jar'
    if (Test-Path -LiteralPath $cachedGson) { $dummyArguments += @('--gson', $cachedGson) }
    if ($DownloadGson) { $dummyArguments += '--download-gson' }
    & python @dummyArguments
    if ($LASTEXITCODE -ne 0) { throw 'Java dummy fixture preparation failed' }
}
$arguments = @('-batchmode', '-nographics', '-projectPath', $project, '-logFile', (Join-Path $artifacts "$Mode.log"))
if ($Mode -in @('EditMode', 'PlayMode')) {
    $results = Join-Path $artifacts "$($Mode.ToLowerInvariant()).xml"
    if (Test-Path -LiteralPath $results) { Remove-Item -LiteralPath $results }
    $arguments += @('-runTests', '-testPlatform', $Mode, '-testResults', $results, '-testFilter', 'Manaforge.Play.Tests')
} else {
    $method = if ($Mode -eq 'Build') { 'WindowsPlayer' } else { 'Prepare' }
    $arguments += @('-quit', '-executeMethod', "Manaforge.Play.Editor.FoundationBuild.$method")
}
Invoke-OwnedProcess $EditorPath $arguments
if ($Mode -in @('EditMode', 'PlayMode')) {
    [xml]$report = Get-Content -LiteralPath $results
    # Counts include printing policy/card components and attached-panel handoff checks.
    $minimum = if ($Mode -eq 'EditMode') { 220 } else { 4 }
    if ($report.'test-run'.result -ne 'Passed' -or [int]$report.'test-run'.total -lt $minimum) {
        throw "Missing or failed $Mode acceptance"
    }
    Write-Output "${Mode}: $($report.'test-run'.passed) passed"
}
