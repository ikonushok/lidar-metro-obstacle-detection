# Быстрый запуск плеера для проверяющих

Цель: открыть браузерный плеер со всеми текущими source IDs без ручной перекладки файлов. Алгоритм не дообучается и не меняется: это только подготовка локальных данных, сборка Docker-образа и запуск HTTP-плеера.

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

Для optional ROS2/headless-проверки можно распаковать отдельные bag-каталоги:

```powershell
python .\scripts\prepare_hackathon_datasets.py `
  --extract doubleT_obstacle `
  --extract cloud_with_fake_obj
```

Полная распаковка `new_data` для браузерного плеера не нужна: direct player читает SQLite-части лениво из TAR.

## 3. Подготовить локальные viewer-файлы

Один раз выполните команды из [docs/README_player_setup.md](README_player_setup.md). Они собирают Docker image при необходимости, копируют `three.min.js` / `OrbitControls.js` в `artefacts/stage_4/cpu_viewer/vendor` и создают Fast DDS XML, который проверяет launcher.

## 4. Запустить Docker-плеер

```powershell
docker ps -q --filter "publish=8100" | ForEach-Object { docker stop $_ }
.\scripts\run_stage_2_cpu_player.ps1 `
  -Port 8100 `
  -RailSelectionMethod development_candidate `
  -RailForwardMinM 2 `
  -ForwardExtensionMethod tangent `
  -NoiseFilterMode candidate_baseline_v2 `
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

Собственные synthetic-артефакты проекта сейчас являются development/evaluation-данными в `artefacts/stage_5/synthetic_obstacles` и не являются отдельным source в браузерном catalog. Метод и ограничения описаны в [docs/README_synthetic_obstacles.md](README_synthetic_obstacles.md).

## 5. Быстрая проверка API

```powershell
$datasets = Invoke-RestMethod 'http://localhost:8100/datasets.json'
$datasets | Select-Object id,label
$manifest = Invoke-RestMethod 'http://localhost:8100/api/cpu_sources/cloud_with_fake_obj/manifest.json'
$manifest | Select-Object dataset_id,frame_count,runtime_transport,noise_filter_mode
```

Ожидается `runtime_transport=direct_cpp` и `noise_filter_mode=candidate_baseline_v2`.

## 6. Проверка репозитория перед сдачей

Перед push в публичный репозиторий выполните read-only gate:

```powershell
python .\scripts\check_submission_package.py
```

Скрипт проверяет, что в Git не tracked локальные датасеты, архивы ROS2 bag,
видео, презентации, `.env` и ключи, а также что присутствуют обязательные
файлы сдачи. Для уже зафиксированного release-коммита можно добавить
`--require-clean`.

## Ограничения демо

`UNKNOWN` и отсутствие reportable-кандидата не означают свободный путь. Геометрия и расстояния используют проектные допущения; это хакатонный viewer для проверки воспроизводимости и просмотра, не сертифицированная система управления движением.
