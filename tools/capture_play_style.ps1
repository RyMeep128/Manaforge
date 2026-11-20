param([string]$PlayerPath,[string]$OutputDirectory,[int]$TimeoutSeconds=180)
$ErrorActionPreference='Stop'
$styleRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $PlayerPath){$PlayerPath=Join-Path $styleRoot 'Mtg_Projects/mtg_play_unity/Builds/Windows/ManaforgePlay.exe'}
if(-not $OutputDirectory){$OutputDirectory=Join-Path $styleRoot ('Mtg_Projects/mtg_play_unity/Artifacts/ForgeStyle-'+[guid]::NewGuid().ToString('N').Substring(0,8))}
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
function Assert-CaptureSize([string]$Path,[int]$Width,[int]$Height){
    $stream=[IO.File]::OpenRead($Path)
    try{
        $header=[byte[]]::new(24)
        if($stream.Read($header,0,24) -ne 24 -or $header[0] -ne 137 -or $header[1] -ne 80 -or $header[2] -ne 78 -or $header[3] -ne 71){throw "Invalid PNG capture: $Path"}
        $actualWidth=[Net.IPAddress]::NetworkToHostOrder([BitConverter]::ToInt32($header,16))
        $actualHeight=[Net.IPAddress]::NetworkToHostOrder([BitConverter]::ToInt32($header,20))
        if($actualWidth -ne $Width -or $actualHeight -ne $Height){throw "PNG resolution mismatch: $Path ($actualWidth x $actualHeight)"}
    }finally{$stream.Dispose()}
}
$fixture=Join-Path $styleRoot 'Mtg_Projects/mtg_play/protocol/fixtures/wire-receive-v1.json'
$revision=(git -C $styleRoot rev-parse HEAD).Trim()
if(git -C $styleRoot status --porcelain){$revision+="-working-tree"}
$arguments=@('-manaforgeStyleReview','1','-manaforgeStyleCapture',$OutputDirectory,'-manaforgeStyleTableFixture',$fixture,'-manaforgeRevision',$revision,'-logFile',(Join-Path $OutputDirectory 'player.log'))
$quoted=$arguments | ForEach-Object { if($_ -match '"'){throw 'Embedded quotes are unsupported'}; '"'+$_+'"' }
$process=Start-Process -FilePath $PlayerPath -ArgumentList $quoted -WindowStyle Hidden -PassThru
try {
    if(-not $process.WaitForExit($TimeoutSeconds*1000)){throw 'Owned style capture timed out'}
    if($process.ExitCode -ne 0){throw "Style player exited $($process.ExitCode)"}
    $proof=Get-Content -LiteralPath (Join-Path $OutputDirectory 'resolution-proof.json') -Raw | ConvertFrom-Json
    if($proof.capture_method -ne 'RenderTexture'){throw 'Missing GPU render-target capture evidence'}
    if($proof.sizes.Count -ne 4){throw 'Missing capture resolutions'}
    foreach($size in $proof.sizes){
        if($size.requested_width -ne $size.observed_width -or $size.requested_height -ne $size.observed_height){throw 'Observed capture resolution differs from requested size'}
        foreach($mode in @('side-by-side','multi-seat','default-1v1','menu','menu-options','menu-confirm','layout-floating','layout-docked','layout-collapsed','layout-preset-saved','layout-preset-confirm')){
            $path=Join-Path $OutputDirectory "$mode-$($size.requested_width)x$($size.requested_height).png"
            if(-not (Test-Path -LiteralPath $path) -or (Get-Item -LiteralPath $path).Length -eq 0){throw "Missing capture: $path"}
            Assert-CaptureSize $path $size.requested_width $size.requested_height
        }
    }
    $animationProof=Get-Content -LiteralPath (Join-Path $OutputDirectory 'animation-proof.json') -Raw | ConvertFrom-Json
    if($animationProof.captures.Count -ne 80){throw 'Missing animation evidence (10 scenarios, 2 motion modes, 4 resolutions)'}
    foreach($capture in $animationProof.captures){
        $path=Join-Path $OutputDirectory $capture.file
        if(-not (Test-Path -LiteralPath $path) -or (Get-Item -LiteralPath $path).Length -eq 0){throw "Missing animation capture: $path"}
        Assert-CaptureSize $path $capture.width $capture.height
    }
    Write-Output "Synthetic style captures: $OutputDirectory"
} finally {
    if(-not $process.HasExited){$process.Kill($true);$process.WaitForExit()}
    $process.Dispose()
}
