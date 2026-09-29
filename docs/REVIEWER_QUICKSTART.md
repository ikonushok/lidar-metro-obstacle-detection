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

Надпись «Препятствие» / «Возможное препятствие» показывает public C++ detection.
В режиме `baseline_v3` трёхкадровый ранний кандидат поднимается в
`intrusion_candidate_present=true`, поэтому headless JSON, evaluator и плеер
используют один и тот же ранний результат. Максимальное задетектированное
расстояние в доступных пользовательских positive-окнах `cloud_with_fake_obj` —
`68.069 м` от source LiDAR origin (`obj01_2x2_center`, кадр `137`). На кадре
`142` расстояние равно `65.708 м`.

Это решение алгоритма, а не доказательство физического препятствия: 47 красных
кадров `new_data` считаются FP по сообщению пользователя об отсутствии
препятствий. На этом источнике плеер подписывает тревогу как «Ложная тревога».

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

## 8. Подготовка данных для измерений

Следующие замеры используют записи организаторов, а не произвольный bag из
примера запуска на своих данных. Положите три архива `for_hackathon`, `new_data` и
`cloud_with_fake_obj` в `dataset/raw/`; допускаются также `.tar`, `.zst` и
`.tar.zst`. Подготовьте каталог TAR и распакуйте `doubleT_obstacle` внутри Docker:

```powershell
docker build -t lidar-metro-obstacle-detection:submission .
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" `
  --workdir /workspace lidar-metro-obstacle-detection:submission `
  python3 scripts/prepare_hackathon_datasets.py --extract doubleT_obstacle
```

Результат: три TAR в `dataset/for_hackathon/` для плеера и замера дальности;
`metadata.yaml` и `.db3` в `dataset/extracted/doubleT_obstacle/` для ROS2 replay.
Уже подготовленные файлы используются повторно. Данные не скачиваются
автоматически и не включаются в образ. Для проверки сборки без кеша используйте
`docker build --no-cache -t lidar-metro-obstacle-detection:submission .`.

## 9. Измерение быстродействия и дальности

Для проверки быстродействия без плеера запустите detector container в компактном
production/perf режиме и затем выполните измеритель. На Windows для измерителя
нужен установленный Python 3.10+ с launcher `py`; сторонние Python-пакеты на
хосте не нужны. Проверьте `py -3 --version`. Если используете виртуальное
окружение, вместо `py -3` укажите путь к его `python.exe`.

```powershell
.\scripts\run_submission_ros2_demo.ps1 `
  -StopExisting -Rate 1.0 -ReadAheadQueueSize 256 -DiagnosticsDetail summary

py -3 .\scripts\measure_headless_ros2_cpp_performance.py `
  --rate 1.0 --read-ahead-queue-size 256 --expected-messages 201 `
  --collector-timeout-seconds 360 `
  --output-stem headless_ros2_cpp_performance_rate_1p0_queue256_summary_diagnostics
```

Скрипт запускает `ros2 bag play` на паузе, дожидается заполнения очереди,
публикует первый кадр и возобновляет запись. Затем собирает выходные JSON, `processing_ms`,
`docker stats` и сохраняет артефакты в `artefacts/current_model_validation/`.
Очередь `256` вмещает целиком две проверенные короткие записи: `doubleT_obstacle`
(201 сообщение) и `roundT_doubleT` (252). Это устраняет starvation при replay
этих записей через медленный Windows bind mount. Для `doubleT_obstacle`
предварительная загрузка в проверке занимала около двух минут, а пик памяти
контейнера — около **5,2 ГиБ**; у Docker должен оставаться запас памяти для
остальных процессов. Для произвольного большого bag размер очереди выбирайте
с учётом размера облаков и доступной памяти; `256` не гарантирует его загрузку целиком.
Перед завершением player используется `--wait-for-all-acked 5000` (до 5 секунд,
для RELIABLE publisher). QoS подписки детектора остаётся BEST_EFFORT;
это ожидание само по себе не гарантирует доставку каждого кадра.
Этот запуск без `-RecordingPath` выбирает подготовленный `doubleT_obstacle`;
`201` — число сообщений именно этой записи. Для другой записи задайте её путь,
топик и frame в launcher, а фактическое число сообщений из `ros2 bag info` —
через `--expected-messages`. При несовпадении с `received_messages` или ошибке
replay/collector измеритель возвращает ненулевой код; при штатном тайм-ауте
сборщика сохраняет полученные сообщения и отчёт с причиной `timeout`.
`play_wall_seconds` включает подготовку и стартовую паузу, поэтому вычисленная
по нему частота не является чистым FPS детектора. При повторном
замере задайте новый `--output-stem`, чтобы сохранить предыдущие результаты.

Для ручной диагностики можно повторить ту же последовательность с заранее
заполненной очередью. Это отдельная проверка полноты, без `docker stats` и без
управления collector измерителем. Детектор `lidar-detector`
должен уже работать в режиме `summary`.

В первом терминале запустите сборщик (для `doubleT_obstacle` — 201 сообщение):

```powershell
New-Item -ItemType Directory -Force artefacts/current_model_validation | Out-Null
docker exec lidar-detector /ros_entrypoint.sh python3 `
  /app/scripts/headless_ros2_perf_collector.py `
  /stage_3/curve_envelope_candidate 201 360 `
  > artefacts/current_model_validation/replay_complete.json
```

Во втором терминале запустите запись на паузе:

```powershell
docker exec lidar-detector /ros_entrypoint.sh ros2 bag play /data `
  --rate 1.0 --read-ahead-queue-size 256 --start-paused `
  --disable-keyboard-controls --wait-for-all-acked 5000
```

В третьем терминале выполните обе команды. `play_next` дожидается готовности
очереди и публикует первый кадр, затем `resume` запускает оставшуюся запись:

```powershell
docker exec lidar-detector /ros_entrypoint.sh ros2 service call `
  /rosbag2_player/play_next rosbag2_interfaces/srv/PlayNext '{}'
docker exec lidar-detector /ros_entrypoint.sh ros2 service call `
  /rosbag2_player/resume rosbag2_interfaces/srv/Resume '{}'
```

После завершения сборщика проверьте `summary.received_messages` в
`replay_complete.json`: оно должно совпадать с числом сообщений bag. Тайм-аут
`360` задаётся в секундах и должен покрывать ожидание старта и весь replay.
Время collector включает подготовительную паузу и не является FPS детектора.
Медленное чтение через Windows bind mount всё ещё может замедлять replay;
полная доставка сама по себе не доказывает real-time.

Для проверки дальности первого public detection на доступных positive-окнах
используйте тот же Docker/Humble runtime:

```powershell
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" `
  lidar-metro-obstacle-detection:submission `
  bash -lc "source /opt/ros/humble/setup.bash && source /app/install/setup.bash && python3 /workspace/scripts/measure_detection_distances.py --root /workspace --progress"
```

## Ограничения демо

`UNKNOWN` и отсутствие reportable-кандидата не означают свободный путь. Геометрия и расстояния используют проектные допущения; это хакатонный viewer для проверки воспроизводимости и просмотра, не сертифицированная система управления движением.
