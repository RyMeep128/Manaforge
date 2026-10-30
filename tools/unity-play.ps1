param(
    [ValidateSet('Prepare', 'EditMode', 'PlayMode', 'Build', 'Smoke')]
    [string]$Mode = 'Prepare',
    [string]$EditorPath = $env:MANAFORGE_UNITY_EDITOR,
    [int]$TimeoutSeconds = 1200
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
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $process.Kill($true)
        $process.WaitForExit()
        throw "Owned $Mode process exceeded timeout"
    }
    if ($process.ExitCode -ne 0) { throw "$Mode process failed with exit code $($process.ExitCode); inspect Artifacts" }
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
    $minimum = if ($Mode -eq 'EditMode') { 8 } else { 1 }
    if ($report.'test-run'.result -ne 'Passed' -or [int]$report.'test-run'.total -lt $minimum) {
        throw "Missing or failed $Mode acceptance"
    }
    Write-Output "${Mode}: $($report.'test-run'.passed) passed"
}
