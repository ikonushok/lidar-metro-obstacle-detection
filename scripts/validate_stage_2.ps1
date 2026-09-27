$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = Join-Path $projectRoot 'dataset/extracted/doubleT_obstacle'
$artefactRoot = Join-Path $projectRoot 'artefacts/stage_2/player'
$image = 'lidar-mosmetro3d:stage_2-player'

if (-not (Test-Path -LiteralPath $dataRoot)) {
    throw "Bag not found: $dataRoot. Run scripts/extract_stage_1.py first."
}
New-Item -ItemType Directory -Force $artefactRoot | Out-Null

& docker build --progress plain -t $image $projectRoot
if ($LASTEXITCODE -ne 0) { throw "Docker build failed (exit $LASTEXITCODE)" }

& docker run --rm `
    --mount "type=bind,source=$dataRoot,target=/data,readonly" `
    --mount "type=bind,source=$artefactRoot,target=/output" `
    $image python3 scripts/prepare_stage_2_player.py /data --output /output
if ($LASTEXITCODE -ne 0) { throw "Stage 2 inspection failed (exit $LASTEXITCODE)" }

Write-Output "Player data prepared in $artefactRoot. Run ./scripts/run_stage_2_player.ps1 to open it locally."
Write-Output "Record observations in docs/stages/stage_2/stage_2_event_registry.md."
