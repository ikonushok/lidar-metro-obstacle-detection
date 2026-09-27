# Stage 4 — единый C++ CPU-плеер всех источников

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-22. Режим: patch → safety-review → validation. Статус: завершено с ограничениями.

## Задача

- Goal: дать в одном viewer переключатель полного `new_data` и шести bag-сцен из `for_hackathon`; raw cloud и его matching C++ JSON должны оставаться единственным источником overlay.
- Наблюдаемая проблема: текущий CPU viewer обслуживает только `new_data`; шесть сцен доступны лишь как частичные prepared exports либо архивные данные без C++ viewer.
- Non-goals: менять C++ AutoRails/CurveEnvelope, profile/margins/thresholds/default, frame/time contracts, deskew, map, tracking, CUDA, class suppression или safety decision.
- Source of truth: `docs/README_dataset_audit.md`, `docs/README_work_plan.md`, `scripts/serve_stage_2_cpu_catalog.py`, `scripts/cpu_catalog_runtime.py`, `web/stage_4_cpu_viewer.html`, C++ node JSON contract.
- Этап: 4 — сигнализация на видео / C++ viewer.
- Среда: Ubuntu 22.04 + ROS 2 Humble + Docker; локальная CPU Docker проверка.
- Вход: `dataset/for_hackathon/new_data` и `dataset/for_hackathon/for_hackathon`, PointCloud2/cdr. Сцены: `roundT_doubleT`, `squareT_platform_squareT_switch`, `doubleT_platform`, `roundT_squareT_pressureGate_squareT`, `doubleT_obstacle`, `roundT_pressureGate_roundT`.
- Frames/transforms: исходные source frames сохраняются. `hesai_lidar <- hesai_lidar` остаётся существующей экспериментальной геометрией; `lidar_livox` не переименовывается и без подтверждённого контракта не получает geometry fallback.
- Режим: lazy raw archive read; matching C++ CPU JSON per displayed frame; browser не рассчитывает rails/envelope/membership.
- Временная база: identity — source header timestamp + frame; playback интервал берётся только из bag offsets внутри одного источника либо nominal fallback; latency не заявляется.
- Allowed files: `scripts/serve_stage_2_cpu_catalog.py`, узкий archive reader рядом с ним, `scripts/cpu_catalog_runtime.py` только если нужен source-parameter wiring, `web/stage_4_cpu_viewer.html`, `web/stage_4_cpu_player.js`, launcher, узкие tests и этот отчёт.
- Files to avoid: C++ geometry core/node, profile/config, bag contents, ROS2 schemas, CUDA.
- Защищённые контракты: every shown overlay comes from matching C++ JSON; source frame/header identity exact; `UNKNOWN != CLEAR`; unsupported source frame has no axis/bounds/core candidates; no viewer detector; no cross-source playback transition.
- Deliverables: selector с 7 sources; lazy manifests/endpoints; run command; tests HTTP/identity/unsupported frame; report.
- Reviewer: safety geometry review, затем validation review; оба sequential текущим агентом, не independent.
- Validation target: L3 для Docker → archive → C++ → HTTP на representative frames каждого source; не quality/real-time claim.
- Acceptance: selector lists exactly seven sources; each manifest has correct frame count; a `hesai_lidar` frame has matching C++ output; `doubleT_obstacle/lidar_livox` stays `UNKNOWN` with empty geometry; viewer has no geometry computation.
- Stop conditions: потребуется изменить frame/profile/thresholds or C++ output cannot be matched to raw identity.

## Отчёт о завершении

### Что изменено

- `scripts/archive_bag_frames.py`: lazy reader одной named bag-сцены внутри TAR. Одновременно материализуется только активная SQLite-часть; при смене источника предыдущая освобождается.
- `scripts/serve_stage_2_cpu_catalog.py`: каталог ровно из семи источников, source-qualified manifest/frame endpoints и сохранённый старый `/api/cpu_new_data/...` endpoint.
- `web/stage_4_cpu_player_source_selector.js`: селектор маршрутизирует существующий C++ viewer к matching lazy manifest; browser не рассчитывает геометрию. HTML получает script при выдаче сервера.
- `tests/test_stage_4_all_sources_contract.py`: инвентарь и запрет viewer-side geometry в selector.

### Evidence и команды

```powershell
docker run --rm ... python3 -m py_compile scripts/archive_bag_frames.py scripts/serve_stage_2_cpu_catalog.py
node --check web/stage_4_cpu_player_source_selector.js web/stage_4_cpu_player.js
.\scripts\run_stage_2_cpu_player.ps1 -Port 8101 -NoBrowser -RebuildImage
Invoke-WebRequest http://127.0.0.1:8101/datasets.json
python3 -m unittest tests.test_stage_4_all_sources_contract
```

Результаты: Docker Humble build PASS; unit 2/2 PASS; `/datasets.json` и все семь manifests вернули ожидаемые frame counts: 11 271, 252, 877, 345, 545, 201, 268. HTTP C++ replay `roundT_doubleT/0` сохранил `hesai_lidar` identity и дал `CURVE_AXIS_SUPPORTED` (15 pairs). `doubleT_obstacle/0` сохранил `lidar_livox`, но получил C++ `UNKNOWN/UNSUPPORTED_SOURCE_FRAME`, без оси/пар/габарита. Старый `/api/cpu_new_data/1054.json` также PASS с matching `hesai_lidar` result. В браузере селектор показал все 7 источников и загрузил C++ overlay.

### Safety-review (current agent, sequential; not independent)

**PASS_WITH_RISKS.** Viewer получает только raw XYZ и JSON существующего C++ node; source frame/header сверяются в browser. При `lidar_livox` не было переименования frame или geometry fallback: `UNKNOWN` остаётся без оси и не означает свободный путь. Profile/margins/thresholds/default не менялись. Всё внутри поддержанного core остаётся C++ candidate, включая инфраструктуру.

### Validation-review (current agent, sequential; not independent)

**PASS_WITH_RISKS, L3** для Docker → archive → C++ CPU → HTTP → browser selector на перечисленных representative frames. Не выполнен full C++ replay всех 13 759 кадров, не измерялись latency/real-time, качество помех, калибровка или физическая корректность оси. Названия сцен не являются ground truth.

### Использование

Тестовый готовый viewer запущен на `http://localhost:8101/`. Для обычного запуска после остановки старого контейнера: `.\scripts\run_stage_2_cpu_player.ps1 -Port 8099 -NoBrowser -RebuildImage`.
