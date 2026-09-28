# Быстрый запуск плеера для проверяющих

Для запуска с автоматической подготовкой используйте [Docker Compose](../README.md#плеер-с-архивами-организаторов). Ниже описан ручной путь через PowerShell launcher.

Цель: открыть браузерный плеер со всеми текущими source IDs без ручной перекладки файлов. Алгоритм не дообучается и не меняется: это только подготовка локальных данных, сборка Docker-образа и запуск HTTP-плеера.

Для хакатонной проверки без браузера основной маршрут описан в разделе
[Headless ROS2 demo без браузера](#7-headless-ros2-demo-без-браузера):
`ros2 bag play -> curve_envelope_node -> std_msgs/String JSON`. Браузерный
плеер остаётся демонстрационным viewer для просмотра сцен и объяснения
результатов.

## 1. Положить сырые датасеты

Из корня проекта создайте каталог:

```powershell
New-Item -ItemType Directory -Force dataset\raw | Out-Null
```

Положите туда три архива организаторов. Допустимые имена:

```text
dataset/raw/for_hackathon
dataset/raw/new_data
dataset/raw/cloud_with_fake_obj
```

Также допускаются имена с `.tar`, `.zst` или `.tar.zst`. Для плеера итоговые файлы должны стать несжатыми TAR без расширения в `dataset/for_hackathon`.

## 2. Подготовить `dataset/for_hackathon`

Нужен любой Python 3 без сторонних пакетов. На Ubuntu используйте `python3`; на Windows обычно подходит `python` или `py`.

```powershell
python .\scripts\prepare_hackathon_datasets.py
```

Скрипт создаёт `dataset/for_hackathon/for_hackathon`, `dataset/for_hackathon/new_data` и `dataset/for_hackathon/cloud_with_fake_obj`. Если возможно, используются hardlink-и, чтобы не копировать десятки гигабайт; если hardlink недоступен, файл копируется. Если входной файл `.zst`, нужен установленный `zstd`.

Для дополнительной ROS2-проверки можно распаковать отдельные записи:

```powershell
python .\scripts\prepare_hackathon_datasets.py `
  --extract doubleT_obstacle `
  --extract cloud_with_fake_obj
```

Полная распаковка `new_data` для браузерного плеера не нужна: direct player читает SQLite-части лениво из TAR.

## 3. Подготовить локальные viewer-файлы

Один раз выполните команды из [docs/PLAYER_SETUP.md](PLAYER_SETUP.md). Они собирают Docker image при необходимости, копируют `three.min.js` / `OrbitControls.js` в `artefacts/stage_4/cpu_viewer/vendor` и создают Fast DDS XML, который проверяет launcher.

## 4. Запустить Docker-плеер

```powershell
docker ps -q --filter "publish=8100" | ForEach-Object { docker stop $_ }
.\scripts\run_stage_2_cpu_player.ps1 `
  -Port 8100 `
  -RailSelectionMethod development_candidate `
  -RailForwardMinM 2 `
  -ForwardExtensionMethod tangent `
  -NoiseFilterMode baseline_v3 `
  -RebuildImage
```

Откройте [http://localhost:8100/](http://localhost:8100/). В выпадающем списке должны быть:

```text
new_data                         # поезд едет около 20 минут
roundT_doubleT                   # поезд стоит / короткая сцена
squareT_platform_squareT_switch  # поезд стоит / короткая сцена
doubleT_platform                 # поезд стоит / короткая сцена
roundT_squareT_pressureGate_squareT
doubleT_obstacle                 # development-сцена с контрольной помехой
roundT_pressureGate_roundT
cloud_with_fake_obj              # synthetic/fake obstacles от организаторов
```

Собственные synthetic-артефакты проекта используются только как
development/evaluation-данные и не являются отдельным source в браузерном
catalog.

Оранжевая надпись «Возможное препятствие» — экспериментальный сигнал: C++ видит
подходящую по форме группу точек внутри габарита, а плеер показывает её после
трёх кадров подряд с кандидатом. Это не подтверждённая тревога; `status` может
оставаться `UNKNOWN`. Плеер не проверяет, что во всех трёх кадрах это один объект.
Красная надпись «Препятствие» и красные точки означают
`intrusion_candidate_present=true` в основном C++ детекторе. Это также не
доказательство физического препятствия: 47 красных кадров `new_data` считаются
FP по сообщению пользователя об отсутствии препятствий. На этом источнике
плеер подписывает красную тревогу как «Ложная тревога».

## 5. Быстрая проверка API

```powershell
$datasets = Invoke-RestMethod 'http://localhost:8100/datasets.json'
$datasets | Select-Object id,label
$manifest = Invoke-RestMethod 'http://localhost:8100/api/cpu_sources/cloud_with_fake_obj/manifest.json'
$manifest | Select-Object dataset_id,frame_count,runtime_transport,noise_filter_mode
```

Ожидается `runtime_transport=direct_cpp` и `noise_filter_mode=baseline_v3`.

## 6. Проверка репозитория перед сдачей

Перед push в публичный репозиторий выполните read-only gate:

```powershell
python .\scripts\check_submission_package.py
```

Скрипт проверяет, что в Git не попали локальные датасеты, архивы записей ROS2,
видео, презентации, `.env` и ключи, а также что присутствуют обязательные
файлы сдачи. Для уже зафиксированного release-коммита можно добавить
`--require-clean`.

## 7. Headless ROS2 demo без браузера

Для сценария жюри `ros2 bag play -> PointCloud2 -> JSON` используйте wrapper:

```powershell
python .\scripts\prepare_hackathon_datasets.py --extract doubleT_obstacle
.\scripts\run_submission_ros2_demo.ps1 -BuildImage -StopExisting
```

Он запускает detector container с `baseline_v3` и печатает команды для
`ros2 topic echo`, `ros2 bag info` и `ros2 bag play`. Для немедленного replay в
том же окне можно добавить `-Play`; для демонстрации JSON-выхода удобнее
оставить replay отдельной командой и параллельно открыть `topic echo`.

По умолчанию wrapper печатает replay-команду с `--rate 0.2` и
`--read-ahead-queue-size 20`: это проверенный demo-режим для большого
записи `doubleT_obstacle` на Windows/Docker bind mount. `--rate 1.0` использовать
только как отдельную throughput-проверку с фиксацией starvation/drops/ресурсов.

Для воспроизводимого замера быстродействия без browser/HTTP player запустите
detector container в compact diagnostics и выполните:

```powershell
.\scripts\run_submission_ros2_demo.ps1 `
  -StopExisting `
  -Rate 1.0 `
  -ReadAheadQueueSize 20 `
  -DiagnosticsDetail summary

python .\scripts\measure_headless_ros2_cpp_performance.py `
  --rate 1.0 `
  --read-ahead-queue-size 20 `
  --expected-messages 201 `
  --collector-timeout-seconds 210 `
  --output-stem headless_ros2_cpp_performance_rate_1p0_summary_diagnostics
```

Скрипт сам запускает `ros2 bag play /data`, слушает JSON-выход detector node,
считает p50/p95/p99/max по `processing_ms`, снимает `docker stats` и пишет
артефакты в `artefacts/current_model_validation/`.

## Ограничения демо

`UNKNOWN` и отсутствие reportable-кандидата не означают свободный путь. Геометрия и расстояния используют проектные допущения; это хакатонный viewer для проверки воспроизводимости и просмотра, не сертифицированная система управления движением.
