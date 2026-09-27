# Подготовка прямого CPU-плеера

Статус: актуальные предусловия `development_candidate / tangent / model_v1`, 2026-09-23. [Основной запуск и headless ROS2](../README.md). Эта страница описывает существующие требования launcher, не меняет код и не включает работы по его автоматизации.

## Данные

Из корня проекта проверьте два полученных от поставщика файла:

```powershell
Get-Item -LiteralPath 'dataset/for_hackathon/for_hackathon', 'dataset/for_hackathon/new_data', 'dataset/for_hackathon/cloud_with_fake_obj'
```

Все три — TAR без расширения. Первый содержит `for_hackathon/<scene>/metadata.yaml` и SQLite, второй — `new_data/metadata.yaml` и SQLite-части, третий — `cloud_with_fake_obj/metadata.yaml` и SQLite. Сервер создаёт каталог всех источников при старте; отсутствующий архив из каталога мешает запуску даже для просмотра только первой сцены. Полная предварительная распаковка плееру не нужна: нужная SQLite-часть извлекается лениво.

Если у вас исходный `for_hackathon.zst`, сначала выполните инструкцию поставщика для этой упаковки. Не переименовывайте сжатый zst в TAR без распаковки. Подробный [состав и границы данных](DATASETS_AND_ASSUMPTIONS.md). Данные не входят в Git и Docker image; команды ниже их не скачивают.

## Локальные файлы, необходимые launcher

Нужны Docker Desktop с Linux containers и доступ к базовому образу/APT при сборке. PowerShell, корень проекта:

```powershell
docker build -t lidar-mosmetro3d:stage-4-cpu-viewer .
if ($LASTEXITCODE -ne 0) { throw 'Docker build failed' }
$projectRoot = (Get-Location).Path
$vendorDir = Join-Path $projectRoot 'artefacts/stage_4/cpu_viewer/vendor'
New-Item -ItemType Directory -Force -Path $vendorDir | Out-Null
docker run --rm --mount "type=bind,source=$vendorDir,target=/output" `
  lidar-mosmetro3d:stage-4-cpu-viewer python3 -c "from pathlib import Path; import shutil; pairs=[('/usr/share/javascript/three/three.min.js','/output/three.min.js'),('/usr/share/javascript/three/examples/js/controls/OrbitControls.js','/output/OrbitControls.js')]; [shutil.copyfile(a,b) for a,b in pairs if not Path(b).exists()]"
if ($LASTEXITCODE -ne 0) { throw 'Viewer asset preparation failed' }
```

Библиотеки установлены APT в Docker-образе. Копируются только отсутствующие файлы; отдельный exporter/replay для получения assets не требуется.

Текущий launcher также требует XML Fast DDS даже в direct-режиме, где DDS-транспорт не используется. Если файла ещё нет, создайте профиль, соответствующий существующему `smoke_udp`:

```powershell
$profile = Join-Path $projectRoot 'artefacts/stage_3/cpp_envelope_core/fastdds_udp_smoke.xml'
if (-not (Test-Path -LiteralPath $profile)) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $profile) | Out-Null
  $xml = @'
<?xml version="1.0" encoding="UTF-8"?>
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor><transport_id>smoke_udp</transport_id><type>UDPv4</type></transport_descriptor>
  </transport_descriptors>
  <participant profile_name="smoke_udp_participant" is_default_profile="true">
    <rtps>
      <userTransports><transport_id>smoke_udp</transport_id></userTransports>
      <useBuiltinTransports>false</useBuiltinTransports>
    </rtps>
  </participant>
</profiles>
'@
  [IO.File]::WriteAllText($profile, $xml, [Text.UTF8Encoding]::new($false))
}
Get-Item -LiteralPath $profile, (Join-Path $vendorDir 'three.min.js'), (Join-Path $vendorDir 'OrbitControls.js')
```

После этого выполните [команду плеера](../README.md#c-cpu-player-прямой-запуск-алгоритма). Для headless ROS2 эти локальные viewer-файлы не нужны; его SHM-профиль находится внутри образа и не заменяется этим UDP XML.

## Проверки и ограничения

Предусловия сверены с launcher/server/Dockerfile/exporter; команды проверяются синтаксически в задаче D0–D3. Чистая сборка, копирование и полный запуск из пустого checkout здесь не выполнялись. Не выдавать эту проверку текста за runtime acceptance. Первый доступ/смена SQLite-части может быть медленнее тёплого; `-RebuildImage` не очищает ожидания и не создаёт dataset/artefacts. Следующий минимальный тест воспроизводимости — выполнить эту последовательность в отдельном чистом checkout с предоставленными архивами.
