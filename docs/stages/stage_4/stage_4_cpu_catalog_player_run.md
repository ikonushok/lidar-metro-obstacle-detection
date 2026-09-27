# C++ CPU catalog player — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 4. Границы: [task spec](stage_4_cpu_catalog_player.md).

## Что изменено

- `scripts/run_stage_2_cpu_player.ps1` теперь запускает lazy C++ CPU catalog, а не трёхкадровый статический export. Плеер доступен для всех 11 271 кадров `new_data`.
- Добавлены `CpuCatalogRuntime`, HTTP catalog и отдельный измеритель последовательного диапазона. На выбранном кадре runtime посылает исходный `PointCloud2` в C++ node и отдаёт browser только matching JSON node плюс неизменённый XYZ.
- Viewer получает metadata/result по запросу, поэтому полный архив не выгружается в браузер. Полный catalog открывается с проверенного кадра 1050, а не с кадра 0, распаковка первого archive chunk которого задерживала первый экран. При отсутствии `bag_offset_seconds` плеер использует 0,1 с как nominal playback interval и не зависает.
- В C++ viewer возвращены практические controls прежнего player: скорости 0,25–4×, ползунок и поле номера кадра, виды камеры, размер точек, browser-кэш трёх последних кадров, отметки, измерения, переключение C++ слоёв, очистка/экспорт annotations и экспорт matching C++ JSON. Они управляют только просмотром. Старые controls ручной оси, margins и live JS membership намеренно не активируются: ось, габарит, кандидаты и distance должны приходить из единственного C++ backend.
- Статический трёхкадровый viewer сохранён в `scripts/run_stage_4_cpu_viewer.ps1` как быстрый smoke/demo; основной launcher теперь `run_stage_2_cpu_player.ps1`.

## Evidence и команды

- `docker build -t lidar-mosmetro3d:stage-4-cpu-viewer -f Dockerfile .` — PASS.
- `docker run ... python3 /verify/tests/test_run_stage_2_cpu_player.py -v` — PASS: 2 tests. До исправления тест фиксировал отсутствие параметров диапазона и жёсткие 1050–1150; после исправления launcher и exporter выбирают непрерывное окно.
- JavaScript из `web/stage_4_cpu_viewer.html` извлечён во временный `.js` и проверен `node --check` — PASS.
- После смены стартового кадра launcher перезапущен; `GET /api/cpu_new_data/1050.json` — PASS, `OBSERVED_CORE_INTRUSION_CANDIDATE`, 78,16 мс, `core_count=585`.
- После возврата controls JavaScript повторно проверен `node --check` — PASS.
- Docker image пересобран после добавления server route для UI. HTTP-проверка: `/` 200, `/stage_4_cpu_player.js` 200; HTML содержит review panel, JS — C++ JSON export.
- C++ JSON дополнен `margin_source_indices` без изменения Axis, profile, bounds, thresholds или membership. После остановки конфликтующего временного ROS2 node проверен кадр 1050: `core_count=585`, `margin_count=20981`, `margin_source_indices=20981`; matching C++ result показывает все нужные source indices.
- Viewer отображает пары левого/правого рельса, C++ margin/core labels, режим `Только внутри core`, C++ counters и подписи distance `source_s_m` вдоль CurveRailAxis. HTTP проверка `/`, main JS, controls JS и axis-labels JS — 200; кадр 1050: 15 rail pairs, 585 core, 20 981 margin indices.
- `./scripts/run_stage_2_cpu_player.ps1 -Port 8099 -NoBrowser` — PASS. `GET /manifest.json` вернул `frame_count=11271`.
- `GET /api/cpu_new_data/1050.json` — PASS: `hesai_lidar`, `OBSERVED_CORE_INTRUSION_CANDIDATE`, `core_count=585`, node 78,45 мс, wall 87,41 мс.
- `./scripts/run_stage_2_cpu_player.ps1 -Port 8099 -NoBrowser -Measure -FirstIndex 1050 -LastIndex 1150` — PASS. Результат: `artefacts/stage_4/cpu_catalog_metrics.json`.
- После замера `GET /api/cpu_new_data/1150.json` — PASS: полный manifest 11 271, C++ CPU, `OBSERVED_CORE_INTRUSION_CANDIDATE`, 76,16 мс, `core_count=396`.
- `GET /api/cpu_new_data/1054.json` — PASS: `UNKNOWN`, `MISSING_CURVE_AXIS`; значение не преобразовано в `CLEAR` или отсутствие предупреждения о неизвестности.

## Замер 1050–1150

Это 101 последовательный development-window кадр. Данные не являются измерением соответствия требованиям real-time или тестового стенда.

| Метрика | Значение |
|---|---:|
| C++ node p50 | 78,27 мс |
| C++ node p95 | 84,61 мс |
| C++ node max | 92,61 мс |
| Wall p50 | 192,38 мс |
| Wall p95 | 291,74 мс |
| Wall max | 351,24 мс |
| Средняя wall частота | 5,21 FPS |

Один кадр (1054) вернул `UNKNOWN`; он остаётся отдельным состоянием и не включён в node latency, поскольку C++ JSON не содержит `processing_ms` для отсутствующей опоры.

## Запуск

Из корня проекта в PyCharm Terminal / PowerShell:

```powershell
# Полный new_data catalog через C++ CPU node.
.\scripts\run_stage_2_cpu_player.ps1 -NoBrowser
Start-Process 'http://localhost:8094/'
```

```powershell
# Непрерывный замер и затем запуск viewer на другом свободном порту.
.\scripts\run_stage_2_cpu_player.ps1 -NoBrowser -Port 8099 -Measure -FirstIndex 1050 -LastIndex 1150
Start-Process 'http://localhost:8099/'
```

Остановка: `docker stop lidar-cpu-catalog-8099`. Для пересборки image добавьте `-RebuildImage` (совместимый алиас: `-RebuildResults`). Старый `run_stage_2_player.ps1` остаётся прежним JS-плеером, поэтому для C++ результата его не использовать.

## Safety-review

Последовательный safety-review текущим агентом: **PASS_WITH_RISKS**.

- Цвет, warning, ось, габарит и расстояние берутся только из C++ JSON; browser не выполняет membership или другой детектор.
- Показ запрещён при несовпадении `source_frame` или `header_timestamp_ns`.
- `UNKNOWN` показывает «путь не объявляется свободным».
- Риск прежний: рабочий frame и bounds остаются `ASSUMED`; core returns — кандидаты, не подтверждённые посторонние объекты.

## Validation-review

Последовательный validation-review текущим агентом: **PASS_WITH_RISKS, L1** для Docker → ROS2 CPU → HTTP catalog цепочки на 101 development-window кадре.

Не проверены ручной WebGL playback, видео, полный диапазон 11 271 кадра, queue/drops, чистая Ubuntu 22.04/Humble машина, результат на хакатонном стенде и TP/FP/FN. Требование real-time пока не заявляется выполненным: wall p95 291,74 мс получен на локальной машине и включает ROS2 round-trip, но не archive/browser/render.

## Следующий минимальный тест

Открыть `http://localhost:8099/`, перейти на 1050, 1054 и 1150, проверить visual warning и `UNKNOWN`; затем выбрать контрольные прямой участок, поворот, низкое препятствие и потерю опоры по спецификации для оценки качества.
