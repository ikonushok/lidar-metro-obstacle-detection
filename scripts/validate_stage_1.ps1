$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = Join-Path $projectRoot 'dataset/extracted'
$outputRoot = Join-Path $projectRoot 'artefacts/stage_1'
New-Item -ItemType Directory -Force $outputRoot | Out-Null
$image = 'lidar-mosmetro3d:stage_1'
function Invoke-CheckedDocker {
    param([string]$Log, [string[]]$DockerArgs)
    & docker @DockerArgs 2>&1 | Tee-Object -FilePath (Join-Path $outputRoot $Log)
    if ($LASTEXITCODE -ne 0) { throw "Docker failed: $Log (exit $LASTEXITCODE)" }
}
Invoke-CheckedDocker -Log 'tests.log' -DockerArgs @('run','--rm',$image,'python3','-m','unittest','discover','-s','tests','-v')
Invoke-CheckedDocker -Log 'environment.log' -DockerArgs @('run','--rm',$image,'bash','-c','cat /etc/os-release; python3 --version; printenv ROS_DISTRO; dpkg-query -W python3-numpy python3-matplotlib ros-humble-rclpy; uname -a')
foreach ($entry in @(@('roundT_doubleT','/lidar_points'), @('doubleT_obstacle','/sensing/lidar/hesai128/pointcloud'))) {
    $bag = $entry[0]
    $topic = $entry[1]
    $mounts = @('--mount',"type=bind,source=$dataRoot,target=/data,readonly",'--mount',"type=bind,source=$outputRoot,target=/output")
    Invoke-CheckedDocker -Log "$bag-audit.log" -DockerArgs (@('run','--rm') + $mounts + @($image,'python3','scripts/audit_bag.py',"/data/$bag",'--output',"/output/$bag"))
    Invoke-CheckedDocker -Log "$bag-replay.log" -DockerArgs (@('run','--rm','--shm-size=512m','-e','ROS_LOCALHOST_ONLY=1') + $mounts + @($image,'python3','scripts/replay_smoke.py',"/data/$bag",'--topic',$topic,'--stage-local','--output',"/output/$bag"))
}
# Prove that the input path is configurable without rebuilding or editing code.
Invoke-CheckedDocker -Log 'alternate-path.log' -DockerArgs @('run','--rm','--shm-size=512m','-e','ROS_LOCALHOST_ONLY=1','--mount',"type=bind,source=$dataRoot/roundT_doubleT,target=/different-bag,readonly",'--mount',"type=bind,source=$outputRoot,target=/output",$image,'python3','scripts/replay_smoke.py','/different-bag','--topic','/lidar_points','--stage-local','--output','/output/alternate-path')
