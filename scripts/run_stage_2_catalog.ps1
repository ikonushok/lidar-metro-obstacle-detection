param([int]$Port=8080,[switch]$NoBrowser,[string]$BagName='doubleT_obstacle')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$image='lidar-mosmetro3d:stage_2-player'
& docker image inspect $image --format '{{.Id}}' | Out-Null
if($LASTEXITCODE -ne 0){throw 'Existing stage_2-player image required. Build it with docker build -t lidar-mosmetro3d:stage_2-player .'}
$name="lidar-player-catalog-$Port"
$running=@(& docker ps --filter "publish=$Port" --format '{{.ID}}')
foreach($id in $running){
    $info=(& docker inspect $id | ConvertFrom-Json)[0]
    $own=@($info.Mounts | Where-Object {
        ($_.Destination -eq '/workspace' -and [IO.Path]::GetFullPath($_.Source) -eq [IO.Path]::GetFullPath($root)) -or
        ($_.Destination -eq '/output' -and [IO.Path]::GetFullPath($_.Source) -eq [IO.Path]::GetFullPath((Join-Path $root 'artefacts/stage_2/player_doubleT_obstacle')))
    })
    if(!$own.Count){throw "Port $Port belongs to another server; use another -Port"}
    if($info.Name -eq "/$name"){
        Write-Output "Catalog already available: http://localhost:$Port/?dataset=$BagName&v=datasets-1"
        if(!$NoBrowser){Start-Process "http://localhost:$Port/?dataset=$BagName&v=datasets-1"}
        return
    }
    & docker stop $id | Out-Null
    if($LASTEXITCODE -ne 0){throw 'Could not stop previous project player'}
}
& docker run --rm -d --name $name --publish "127.0.0.1:${Port}:8000" `
    --mount "type=bind,source=$root,target=/workspace,readonly" `
    --env 'PYTHONPATH=/workspace/src' $image python3 /workspace/scripts/serve_stage_2_catalog.py
if($LASTEXITCODE -ne 0){throw 'Dataset server failed to start'}
Write-Output "Catalog: http://localhost:$Port/?dataset=$BagName&v=datasets-1 (stop: docker stop $name)"
if(!$NoBrowser){Start-Process "http://localhost:$Port/?dataset=$BagName&v=datasets-1"}
