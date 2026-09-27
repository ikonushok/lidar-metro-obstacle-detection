$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = Join-Path $projectRoot 'dataset/extracted/doubleT_obstacle'
$artefactRoot = Join-Path $projectRoot 'artefacts/stage_3'
$image = 'lidar-mosmetro3d:stage_3_baseline'

if (-not (Test-Path -LiteralPath $dataRoot)) {
    throw "Bag not found: $dataRoot. Run scripts/extract_stage_1.py first."
}
New-Item -ItemType Directory -Force $artefactRoot | Out-Null

& docker build --progress plain -t $image $projectRoot
if ($LASTEXITCODE -ne 0) { throw "Docker build failed" }

& docker run --rm $image python3 -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed" }

& docker run --rm --shm-size=512m -e ROS_LOCALHOST_ONLY=1 `
    --mount "type=bind,source=$dataRoot,target=/data,readonly" `
    --mount "type=bind,source=$artefactRoot,target=/output" `
    $image python3 scripts/replay_stage_3_baseline.py /data `
        --input-topic /sensing/lidar/hesai128/pointcloud --stage-local --output /output
if ($LASTEXITCODE -ne 0) { throw "Stage 3 replay failed" }
