# CUDA backend для CurveRailAxis envelope

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation, этап 3.

- Goal: добавить опциональный CUDA backend, который параллельно классифицирует исходные XYZ по неизменённым сегментам CurveRailAxis.
- Проблема: CPU C++ kernel уже быстрый на выбранном окне, но GPU предусмотрен стендом ТЗ и нужен как измеряемое опциональное ускорение массовой классификации на NVIDIA.
- Non-goals: изменение AutoRails, CurveRailAxis, профиля, margins, порогов, семантики зон, кластеризации, TF/extrinsics, deskew, map, tracking, TTC, CUDA-only обязательность или утверждение о real-time.
- Source of truth: C++ CPU core, `stage_3_cpp_envelope_core_run.md`, текущие config/reference profile, ТЗ §3.1–3.3 и §8.3.
- Этап: 3, производительность до шага сквозной проверки.
- Целевое окружение: Ubuntu 22.04, ROS2 Humble, Docker, NVIDIA GPU. Локальная фактическая GPU только для проверки, не эквивалент организаторской RTX 4070 Ti SUPER.
- Вход/геометрия: float32 source XYZ, same AutoRails rail_pairs, `hesai_lidar <- hesai_lidar`, метры ASSUMED. GPU не меняет координаты и не использует timestamps.
- Backend: CPU строит и валидирует сегменты; CUDA обрабатывает точки независимо и возвращает только labels. CPU суммирует counts и nearest из returned labels по тем же правилам. Передача XYZ/labels входит в замер. Default runtime backend остаётся `cpu`; `auto`/`cuda` включаются явно после замера на целевом стенде.
- Поведение: no axis/invalid geometry → UNKNOWN до CUDA. GPU failure/unavailable в auto mode → CPU fallback с diagnostic; `cuda` explicitly requested without backend → UNKNOWN, never CLEAR.
- Allowed files: `src/cpp/cuda_envelope.*`, `src/lidar_mosmetro3d_cpp/**`, `Dockerfile.cuda`, tests/benchmark scripts and artefacts under `artefacts/stage_3/cuda_envelope/`, this plan and result report.
- Files to avoid: CPU reference algorithm, profiles/config thresholds, raw/bag, baseline Python/JS behavior, standard CPU Dockerfile.
- Защищённые контракты: same zones/nearest/counters as CPU; low singleton survives; supported segment only; no silent CPU/GPU result substitution in benchmark; CPU fallback named; no CLEAR.
- Deliverables: optional CUDA build, runtime selection, CPU/GPU parity test, GPU timing including transfers, GPU Docker image.
- Reviewer: safety_geometry_reviewer after implementation; validation review after parity and benchmark; both sequential passes current agent, not independent.
- Target validation: L1 for real saved frames and local GPU; L0 for organizer GPU and full bag runtime.
- Acceptance: CPU/GPU exact labels, counts and nearest source indices on saved frames; unavailable GPU does not produce CLEAR; GPU image builds without manual dependencies; report distinguishes kernel from full pipeline latency.
- Stop: any zone/nearest mismatch, unsupported CUDA/driver build, hidden geometry change or unavailable backend mapped to clear state stops GPU activation.
