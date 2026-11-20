# Select existing tools without exporting a license or installing system software.
param(
    [string]$Python = "$env:LOCALAPPDATA/Programs/Python/Python313/python.exe",
    [string]$Jdk = 'C:/Program Files/Java/jdk-23'
)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'self-hosted' -or -not $IsWindows) {
    throw 'Personal Unity CI requires an explicitly approved self-hosted Windows Actions runner'
}
if ($env:GITHUB_EVENT_NAME -ne 'workflow_dispatch' -or $env:GITHUB_REF -ne 'refs/heads/main' -or $env:GITHUB_ACTOR -ne $env:GITHUB_REPOSITORY_OWNER) {
    throw 'Personal Unity CI is restricted to repository-owner manual dispatches of main'
}
$project = Join-Path $PSScriptRoot '../Mtg_Projects/mtg_play_unity'
$versionLine = Get-Content (Join-Path $project 'ProjectSettings/ProjectVersion.txt') | Select-String '^m_EditorVersion: '
$editorVersion = $versionLine.ToString().Split(' ')[1]
$editor = "C:/Program Files/Unity/Hub/Editor/$editorVersion/Editor/Unity.exe"
if (-not (Test-Path -LiteralPath $editor)) { throw "Activate the pinned Unity editor in Unity Hub first: $editorVersion" }
if (-not (Get-Item -LiteralPath $editor).VersionInfo.ProductVersion.StartsWith($editorVersion)) {
    throw 'The existing Unity editor does not match the project pin'
}
"MANAFORGE_UNITY_EDITOR=$editor" | Out-File -LiteralPath $env:GITHUB_ENV -Encoding utf8 -Append
if (-not (Test-Path -LiteralPath $Python)) { throw 'An existing Python 3.12 or 3.13 installation is required' }
$pythonVersion = & $Python --version
if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3\.(12|13)\.') { throw 'Unsupported existing Python version' }
$java = Join-Path $Jdk 'bin/java.exe'
if (-not (Test-Path -LiteralPath $java)) { throw 'The existing pinned JDK 23.0.2+7 is required' }
$javaVersion = (& $java -version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $javaVersion -notmatch '23\.0\.2\+7') { throw 'The existing JDK does not match the CI pin' }
$venv = Join-Path $env:RUNNER_TEMP 'manaforge-python'
& $Python -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the temporary Actions Python environment' }
(Join-Path $venv 'Scripts') | Out-File -LiteralPath $env:GITHUB_PATH -Encoding utf8 -Append
(Join-Path $Jdk 'bin') | Out-File -LiteralPath $env:GITHUB_PATH -Encoding utf8 -Append
"JAVA_HOME=$Jdk" | Out-File -LiteralPath $env:GITHUB_ENV -Encoding utf8 -Append
Write-Output 'Selected the existing Unity Hub installation. Subsequent builds and tests must validate its license.'
