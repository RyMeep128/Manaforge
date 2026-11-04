# Install only on disposable GitHub-hosted Windows machines. Never log activation output.
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or -not $IsWindows) {
    throw 'Unity CI setup requires a GitHub-hosted Windows runner'
}
foreach ($name in @('UNITY_LICENSE', 'UNITY_EMAIL', 'UNITY_PASSWORD')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Missing Actions secret $name. Configure repository Actions secrets; see docs/unity-ci.md."
    }
}
$projectVersion = Get-Content (Join-Path $PSScriptRoot '../Mtg_Projects/mtg_play_unity/ProjectSettings/ProjectVersion.txt') -Raw
if ($projectVersion -notmatch 'm_EditorVersionWithRevision: 6000\.6\.7f1 \(b22767f04f04\)') {
    throw 'Update the verified Unity installer pin when changing the project editor version'
}
$installer = Join-Path $env:RUNNER_TEMP 'UnitySetup64-6000.6.7f1.exe'
$installRoot = Join-Path $env:RUNNER_TEMP 'Unity/6000.6.7f1'
$editor = Join-Path $installRoot 'Editor/Unity.exe'
$licenseFile = Join-Path $env:RUNNER_TEMP 'manaforge-ci-license.ulf'
$activationLog = Join-Path $env:RUNNER_TEMP 'manaforge-ci-activation.log'

function Invoke-PrivateProcess([string]$Executable, [string[]]$Arguments, [int]$TimeoutSeconds) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw 'Unity installation or activation timed out'
        }
        # Output may contain credentials or license information; deliberately discard it.
        $null = $stdout.GetAwaiter().GetResult()
        $null = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "Unity installation or activation failed (exit $($process.ExitCode)). Verify the Personal license secrets and Unity activation eligibility."
        }
    } finally { $process.Dispose() }
}

try {
    Write-Output 'Downloading pinned Unity 6000.6.7f1 Windows editor'
    Invoke-WebRequest 'https://download.unity3d.com/download_unity/b22767f04f04/Windows64EditorInstaller/UnitySetup64-6000.6.7f1.exe' -OutFile $installer
    $digest = [Convert]::ToBase64String([Convert]::FromHexString((Get-FileHash -LiteralPath $installer -Algorithm MD5).Hash))
    if ($digest -ne 'dWiAKKZ/Yiu5xQ9tLQvXRA==') { throw 'Unity installer integrity mismatch' }
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Unity Technologies') {
        throw 'Unity installer publisher signature validation failed'
    }
    # NSIS requires /D to be the final argument.
    Invoke-PrivateProcess $installer @('/S', "/D=$installRoot") 1200
    if (-not (Test-Path -LiteralPath $editor)) { throw 'Pinned Unity editor was not installed' }
    if ((Get-Item -LiteralPath $editor).VersionInfo.ProductVersion -notlike '6000.6.7f1*') {
        throw 'Installed Unity editor version differs from the project pin'
    }
    [IO.File]::WriteAllText($licenseFile, $env:UNITY_LICENSE)
    Invoke-PrivateProcess $editor @('-batchmode', '-nographics', '-quit', '-manualLicenseFile', $licenseFile,
        '-username', $env:UNITY_EMAIL, '-password', $env:UNITY_PASSWORD, '-logFile', $activationLog) 300
    "MANAFORGE_UNITY_EDITOR=$editor" | Out-File -LiteralPath $env:GITHUB_ENV -Encoding utf8 -Append
    Write-Output 'Pinned Unity editor installed and activation command completed; test execution will validate license availability'
} finally {
    foreach ($privateFile in @($installer, $licenseFile, $activationLog)) {
        if (Test-Path -LiteralPath $privateFile) { Remove-Item -LiteralPath $privateFile -Force }
    }
}
