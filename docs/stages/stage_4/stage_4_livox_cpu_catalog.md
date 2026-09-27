# Stage 4 — C++ CPU viewer для `doubleT_obstacle` / `lidar_livox`

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер. ROS_DOMAIN_ID=(port%232)+1 не гарантирует изоляцию всех портов: значения повторяются через 232; direct_cpp не использует DDS для кадра.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-22. Режим: patch → safety-review → validation. Статус: выполнено с ограничениями.

## Задача

- Goal: показать для `doubleT_obstacle` C++-результат поиска рельс, ось, assumed габарит, core/margin-кандидаты и ближайшее расстояние в общем CPU viewer.
- Наблюдаемая проблема: `scripts/cpu_catalog_runtime.py` всегда запускает node с `source_frame:=hesai_lidar`; поэтому корректно сохранённый raw `lidar_livox` frame завершается `UNKNOWN/UNSUPPORTED_SOURCE_FRAME` до анализа рельс.
- Non-goals: менять XYZ, переименовывать frame, менять профиль, margins, thresholds, AutoRails/CurveEnvelope, TF, deskew, карту, tracking, CUDA или объявлять свободный путь.
- Source of truth: `config/geometry_contract.yaml`, `docs/README_dataset_audit.md`, C++ node JSON contract, `scripts/cpu_catalog_runtime.py` и CPU catalog viewer.
- Этап: 4 — C++ viewer / демонстрация.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка — Docker CPU viewer.
- Вход: `doubleT_obstacle`, 201 PointCloud2 frames, source frame `lidar_livox`; XYZ остаются в source coordinates. Единицы, оси и envelope — `ASSUMED_HACKATHON`.
- Рабочие frames и transform: `hackathon_track_lidar_livox <- lidar_livox` — identity only under existing `ASSUMED_HACKATHON` contract; C++ JSON и raw cloud сохраняют исходный `lidar_livox`.
- Режим: candidate-only; `safety_decision_permitted=false`; отсутствие оси остаётся `UNKNOWN`, не `CLEAR`.
- Временная база: сопоставление только source header timestamp; CPU wall time — `time.monotonic()` вокруг ROS2 request/result.
- Allowed files: `scripts/cpu_catalog_runtime.py`, `scripts/serve_stage_2_cpu_catalog.py`, узкие tests и этот отчёт.
- Files to avoid: C++ geometry core/node, geometry profile/config, ROS2 schemas, raw data and archives.
- Защищённые контракты: source frame и header exact between cloud/result; browser has no geometry computation; result uses the per-frame source frame; no `CLEAR`.
- Deliverables: dynamic source-frame wiring; ROS2 isolation per viewer; neutral catalog label; test; Docker HTTP replay of a `lidar_livox` frame.
- Основной агент: current agent, `agents/lidar_obstacle_pipeline.md`.
- Safety-review: required because source-frame handling enables geometry candidate output; sequential current-agent review after the change.
- Validation-review: required after safety-review; check claim only for one end-to-end C++/HTTP frame, not detection quality.
- Validation target: L3 for Docker → archive → C++ → HTTP on representative `doubleT_obstacle` frame.
- Acceptance: a `lidar_livox` result keeps its identity, is not `UNSUPPORTED_SOURCE_FRAME`, has a C++ result consistent with rail support or `MISSING_CURVE_AXIS`, and never permits safety decision.
- Stop conditions: source frame differs inside a bag without safe runtime restart, C++ result identity mismatches raw frame, or contract requires changed geometry bounds.

## Отчёт о завершении

- Что изменено:
  - `CpuCatalogRuntime` запускает C++ node с фактическим `record['source_frame']` и корректно пересоздаёт node при смене frame между источниками.
  - Каждый экземпляр launcher получает собственный `ROS_DOMAIN_ID`, детерминированно полученный из порта. Это исключает получение C++ JSON от viewer на другом порту, который использует те же ROS2 topic names.
  - Название `doubleT_obstacle` в selector теперь отражает `assumed geometry`, а не заранее утверждает `UNKNOWN`.
- Evidence inspected: `config/geometry_contract.yaml` (`lidar_livox: ASSUMED_HACKATHON_ACTIVE`, `hackathon_track_lidar_livox <- lidar_livox`, профиль `[-1.4, 1.4] × [0.0, 3.7]`); `scripts/cpu_catalog_runtime.py`; C++ node and JSON contract; stage-4 catalog report.
- Commands run:
  - Docker unit tests `tests.test_stage_4_all_sources_contract`, `tests.test_cpu_catalog_runtime_source_frame`, `tests.test_run_stage_2_cpu_player` — PASS, 6 tests.
  - `./scripts/run_stage_2_cpu_player.ps1 -Port 8099 -NoBrowser -RebuildImage` — PASS; Humble C++ package rebuilt.
  - HTTP C++ frame `doubleT_obstacle/168` — `CURVE_AXIS_SUPPORTED`, 14 rail pairs, `core_count=916`, `margin_count=14138`, candidate status, `lidar_livox`, `safety_decision_permitted=false`.
  - HTTP C++ frame `doubleT_obstacle/200` — `CURVE_AXIS_SUPPORTED`, 17 rail pairs, `core_count=1009`, `margin_count=15780`, nearest core candidate 4.24 m from source origin, `safety_decision_permitted=false`.
- Safety-review (current agent, sequential; not independent): PASS_WITH_RISKS. Source frame is passed unchanged and identity is still checked by browser. The change does not rename frame, change profile/bounds/margins, or create a `CLEAR` result. `MISSING_CURVE_AXIS` remains `UNKNOWN`. Risk: the active geometry is deliberately `ASSUMED_HACKATHON`; all core returns are candidates, including possible infrastructure returns.
- Validation-review (current agent, sequential; not independent): PASS_WITH_RISKS, L3 for Docker → archive → C++ → HTTP on two real `doubleT_obstacle` frames. It proves the viewer receives matching source-frame C++ geometry, not obstacle classification quality or a safety decision.
- Что не проверено: full 201-frame C++ replay; TP/FP/FN event matching; physical calibration of frame/profile; latency and dropped frames; manual WebGL visual review after browser refresh.
- Известные FP/FN или safety-риски: `core_count` counts returns inside the assumed envelope, not classified objects. An observed core candidate does not identify a person and is not a train-control signal.
- Следующий минимальный тест: browser refresh at `http://localhost:8099/`, select `doubleT_obstacle`, verify rails/axis/train layers on frame 200; then complete a 201-frame candidate and axis-availability summary.
- Residual risk: the ROS domain formula isolates simultaneously launched project viewers by port within the valid ROS2 domain range, but an unrelated process manually assigned the same domain could still interfere.
