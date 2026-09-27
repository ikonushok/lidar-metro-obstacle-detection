# Stage 5 — CPU viewer transport speed fix

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: вернуть быстрый forward playback в C++ CPU viewer без изменения геометрии.
- Наблюдаемая проблема или исходный claim: текущий HTTP viewer считает каждый кадр через ROS2 pub/sub; `processing_ms` около 130 ms, но `wall_processing_ms` прыгает до секунд. Ранее быстрый путь был реализован как direct C++ stream runner, но остался в audit harness.
- Non-goals: не менять профиль, margin, ось, rail-selection алгоритм, frame/units/time, `UNKNOWN` policy, browser membership или safety decision.
- Source of truth: `scripts/cpu_catalog_runtime.py`, `scripts/serve_stage_2_cpu_catalog.py`, `src/cpp/curve_pipeline_stream_cli.cpp`, `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`, `docs/stages/stage_4/stage_4_cpu_catalog_player_run.md`.
- Этап docs/work_plan.md: Stage 5 viewer/runtime diagnostics.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: локальный Docker image/HTTP viewer.
- Входные данные и единицы: source XYZF finite non-zero returns, метры assumed, без transform.
- Рабочие frames и направление transforms: unchanged source frame; identity assumption only where already present.
- Временная база событий и способ измерения вычислительной задержки: process monotonic `wall_processing_ms`; header timestamp copied from source record.
- Allowed files: direct C++ stream CLI, Python CPU catalog runtime/server, narrow tests, this report.
- Files to avoid: raw archive, geometry config, C++ core algorithms, web UI semantics.
- Защищённые контракты: `UNKNOWN != CLEAR`; `safety_decision_permitted=false`; C++ JSON remains single source of axis/envelope/source indices; result header/source frame must match raw frame.
- Deliverables и статус каждого: direct detailed runtime for viewer; ROS2 fallback retained; narrow validation command.
- Основной агент: current agent via `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer`: нет, геометрия и thresholds не меняются.
- Нужен ли отдельный этап `validation_reviewer`: краткий validation pass after smoke.
- Validation target: L1 for transport contract and local smoke, L0 for real-time/browser video.
- Validation method: syntax/unit tests where available and HTTP frame timing smoke.
- Acceptance criteria: viewer JSON contains detailed envelope fields through direct stream; frame/source/header identity match; sequential frame wall latency no longer dominated by ROS2 seconds; fallback still available.
- Stop conditions: mismatch with ROS2 geometry contract, missing source indices/wireframes, any change to safety decision semantics.

## Отчёт о завершении

- Что изменено:
  - `src/cpp/curve_pipeline_stream_cli.cpp` теперь может отдавать detailed viewer JSON: wireframes, rail pairs, core/margin source indices, nearest intrusion and diagnostics.
  - Добавлен optional `--observed-only`, но viewer его не использует: текущий viewer должен совпадать с ROS2 node, включая forward extension fields.
  - `scripts/cpu_catalog_runtime.py` получил `DirectDetailedCpuRuntime`, который запускает `curve_pipeline_stream_cli` и добавляет matching `header_timestamp_ns`/`source_frame` из source record.
  - `scripts/serve_stage_2_cpu_catalog.py` использует direct runtime для `development_candidate`; прежний ROS2 `CpuCatalogRuntime` сохранён как fallback для `baseline`.
- Evidence inspected:
  - Сравнены текущий ROS2 node и direct runtime на `doubleT_obstacle` frame 28.
  - Проверен HTTP catalog на `doubleT_obstacle` frames 29–32.
- Commands run:
  - `docker build -t lidar-mosmetro3d:stage-4-cpu-viewer -f Dockerfile .` — PASS, C++ package built.
  - One-frame Docker comparison ROS2 vs direct on `doubleT_obstacle` frame 28 — PASS for status, reason, curve axis status, rail pair count, observed pair count, extrapolation flag, core/margin/outside/unknown counts, nearest source index and wireframe count.
  - `.\scripts\run_stage_2_cpu_player.ps1 -Port 8100 -NoBrowser -RailForwardMinM 2.0` — PASS after Docker permission escalation.
  - HTTP JSON smoke `doubleT_obstacle` frames 29–32 — first cold frame 17.6 s due source archive/chunk materialization; subsequent frames 124–130 ms HTTP and 59–62 ms direct wall.
  - HTTP XYZ smoke frames 29–32 — 183–264 ms for ~3.95 MB XYZF payloads.
  - Initial `python -m py_compile ...` local attempt — not run: local `python` not in PATH and `py` points to missing Python 3.12.
  - Initial unittest invocation by file path — invalid unittest syntax, failed to import path names.
  - Corrected Docker unittest discovery:
    - `test_stage_4_all_sources_contract.py` — 7/7 OK.
    - `test_cpu_catalog_runtime_source_frame.py` — 4/4 OK.
    - `test_run_stage_2_cpu_player.py` — 4/4 OK.
- Validation level achieved: L1 for local Docker direct-runtime transport and HTTP smoke. No real-time claim.
- Что не проверено:
  - Browser visual playback FPS, WebGL render timing, video capture, long continuous 11 271-frame playback, queue/drops and clean target machine.
  - Full field-by-field JSON equality; checked key geometry/count fields only.
- Известные FP/FN или safety-риски:
  - Не менялись. `UNKNOWN` remains not clear; `safety_decision_permitted=false`.
  - Forward extension was already present in current node contract; this fix preserves it in viewer direct mode.
- Следующий минимальный тест:
  - Manual browser playback on `http://localhost:8100/?dataset=doubleT_obstacle&v=all-sources-1` over a 30–60 frame forward-only segment, recording visible stalls and browser frame rate.
- Residual risk:
  - First frame after switching source can remain slow because `ArchiveBagFrames` materializes a TAR/SQLite part; this is I/O cold start, not C++/ROS2 round-trip.
