# This only selects an existing, locally activated editor. It never exports a license.
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
Write-Output 'Selected the existing Unity Hub installation. Subsequent builds and tests must validate its license.'
