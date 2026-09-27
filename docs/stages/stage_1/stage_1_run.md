# Запуск проверки входа — этап 1

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Это проверка чтения PointCloud2, а не детектор препятствий. Решение о свободном пути не выдаётся. Геометрия, оси, единицы и связь часов пока не откалиброваны.

## Сборка

Из корня проекта, с работающим Linux Docker Engine:

```sh
docker build --progress plain -t lidar-mosmetro3d:stage_1 .
docker run --rm lidar-mosmetro3d:stage_1 python3 -m unittest discover -s tests -v
```

Образ использует Ubuntu 22.04, ROS 2 Humble и системный Python 3.10. Все зависимости устанавливаются при сборке через apt. Локальная старая Windows `.venv` не является средой выполнения; запускать ROS-скрипты внутри контейнера. Тег базового образа и apt-репозитории обновляемые; точные версии конкретной проверки находятся в build.log и environment.log, побитовая воспроизводимость не заявляется.

## Подготовка двух записей

```sh
python scripts/extract_stage_1.py
```

Скрипт требует только стандартную библиотеку Python. Читает исходный TAR `dataset/for_hackathon/for_hackathon`, извлекает только `roundT_doubleT` и `doubleT_obstacle` в `dataset/extracted`. Требуется примерно 6.84 GB свободного места. Существующие файлы не перезаписывает; повторное извлечение уже подготовленных данных не требуется.

## Полная проверка в Windows PowerShell

```powershell
./scripts/validate_stage_1.ps1
```

Последовательно выполняются unit-тесты в контейнере, описание среды, полное offline-чтение обеих записей, настоящий replay через ROS 2/DDS и повторный replay обычной записи с другим путём монтирования. Перед каждым replay bag копируется во временное Linux-хранилище контейнера, чтобы отделить передачу ROS от медленного Windows bind mount. Копия удаляется после проверки; исходник монтируется только для чтения.

Player запускается на паузе. Скрипт ждёт ROS-сервисы и publisher, запрашивает первый кадр и дожидается его обработки; затем продолжает оставшуюся запись с rate=1. Перед завершением player ожидает подтверждения DDS до 30 секунд. Начальный шаг — подготовка стенда, а не измерение задержки обнаружения. Общий timeout replay — 120 секунд, копирование в него не входит.

`config/fastdds.xml` задаёт SHM-сегмент 128 MiB для сообщений 8–24 MB; контейнеру нужен `--shm-size=512m`. Это параметр транспорта проверяемого стенда, не универсальная настройка любых данных. QoS сообщений сохранён. Отдельное увеличение SHM не устранило потери в исходном эксперименте. [Описание SHM Fast DDS](https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/transport/shared_memory/shared_memory.html).

## Отдельный запуск в Linux

```sh
mkdir -p artefacts/stage_1
docker run --rm \
  --mount "type=bind,source=$(pwd)/dataset/extracted,target=/data,readonly" \
  --mount "type=bind,source=$(pwd)/artefacts/stage_1,target=/output" \
  lidar-mosmetro3d:stage_1 python3 scripts/audit_bag.py \
  /data/doubleT_obstacle --output /output/doubleT_obstacle

docker run --rm --shm-size=512m -e ROS_LOCALHOST_ONLY=1 \
  --mount "type=bind,source=$(pwd)/dataset/extracted,target=/data,readonly" \
  --mount "type=bind,source=$(pwd)/artefacts/stage_1,target=/output" \
  lidar-mosmetro3d:stage_1 python3 scripts/replay_smoke.py \
  /data/doubleT_obstacle --topic /sensing/lidar/hesai128/pointcloud \
  --stage-local --output /output/doubleT_obstacle
```

Для обычной записи: путь `/data/roundT_doubleT`, топик `/lidar_points`.

## Результаты и ограничения

- `frames.jsonl`: статистика каждого облака и раздельные bag/header/per-point timestamps.
- `summary.json`: число сообщений, ошибки, доли нулей/невалидных точек, время offline-инспекции и память процесса.
- `cloud_*.png`: три проекции начала, середины и конца записи. Только при отображении исключены нули/NaN и прорежены точки; исходные данные не изменяются.
- `replay.json`, `player.log`: число принятых сообщений, p95 обработки callback, ошибки и лог ros2 bag play.
- QoS подписчика соответствует metadata двух выбранных bag: RELIABLE, VOLATILE, KEEP_LAST depth=10. Для другого publisher проверить совместимость отдельно.
- Счётчики replay сверяются с SQLite; полный список `received_header_ns` позволяет сверить порядок с `frames.jsonl`. Равенство количества само по себе не доказывает отсутствие замен/дубликатов; timestamps не являются универсальным ID.
- Время callback не включает DDS-очередь; p95 offline не включает чтение SQLite. Это не задержка детектора и не доказательство real-time.
- Формат скриптов этапа 1: каталог с единственным `.db3`, PointCloud2/CDR. Разделённые bag и MCAP пока не поддержаны.
- Измерения относятся только к выбранным двум записям и локальному оборудованию. Четыре остальных сценария не прошли эту проверку.
