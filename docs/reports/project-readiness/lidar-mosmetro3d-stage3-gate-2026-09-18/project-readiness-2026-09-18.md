# Project readiness — lidar_MosMetro3D, gate этапа 3

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированный аудит до редакции D0–D3; findings и рекомендации описывают тот срез. Текущие исправления документации указаны в отчёте D0–D3; runtime findings этим не закрыты.
> [Актуальный запуск](../../../../README.md) · [Текущий план](../../../README_work_plan.md) · [Результат D0–D3](../../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->


## Summary

- Verdict: `PASS_WITH_RISKS` to start stage 3; `HOLD` for the stage-3 acceptance claim.
- Readiness stage: technical prototype progressing toward MVP.
- Validation level / evidence level: L1 for input/replay and one visual bag render; L0 for calibrated geometry, event labels and detector quality.
- Validation basis: current source/configuration, existing stage-1/2 runtime records, a direct rerun of the present unit suite, and the original contest specification.
- Audit mode: `docs-vs-code` plus narrow runtime check.
- Target project: `lidar_MosMetro3D`.

ТЗ требует контейнер, подключение к ROS2, чтение bag, обработку облака и вывод результата алгоритма. Проект уже показал контейнерное чтение и replay двух известных входов; stage 2 подготовил полный visual-only рендер одного obstacle bag. Самая важная часть цепочки ТЗ — детекция с выводом результата и расстояния — ещё не реализована, что и составляет содержание этапа 3.

Критерий перехода этапа 2 в `docs/work_plan.md` допускает «согласованный входной контракт либо явно указанный блокер геометрии». Блокер локализован, а текущая ревизия YAML вводит явно ограниченный `ASSUMED_HACKATHON` профиль. Поэтому этап 3 может строить demo-candidate, но не может подменять его `CLEAR` или safety-утверждением.

## Мaturity by capability

| Capability | Статус | Evidence | Readiness |
|---|---|---|---|
| Humble/Docker и входной replay | выполнено на двух известных bag | `docs/stages/stage_1/stage_1_input.md`, code/scripts, контейнер | L1 |
| Полный visual review obstacle | выполнено как visual-only | `docs/stages/stage_2/stage_2_run.md`, renderer | L1 |
| Geometry contract | demo-profile ограничен явно; production calibration отсутствует | `config/geometry_contract.yaml` | L1 config / L0 physical validity |
| Event labels/split protocol | protocol есть, разметки нет | `stage_2_event_registry.md`, `stage_2_evaluation_protocol.md` | L0 |
| Detector/nearest distance/diagnostics | не реализовано | source-tree inspection | absent |
| Метрики, FP/FN, performance detector | не заявляются и не измерены | source/docs inspection | absent |

## Findings

### F1 — HIGH: geometry is a demo assumption, not a safety calibration

- Evidence strength: product/API gap with explicit fail-safe static configuration.
- Evidence: `config/geometry_contract.yaml` defines `ASSUMED_HACKATHON` axes, identity transform, path, rectangle and 0.20 m margin for `lidar_livox`, but requires production replacement evidence and forbids `CLEAR`/safety-decision.
- What is proven: current configuration permits only a labelled demo candidate; it still prevents a safety decision.
- Impact: a demo envelope intersection and approximate distance may be shown, but not an operational clearance or quality claim.
- Next action: obtain primary calibration/profile/path/margin material and perform a safety review before production activation.

### F2 — HIGH: mandatory detector path is absent

- Evidence strength: direct code absence in inspected source tree.
- Evidence: only input/replay subscriber and stage-2 renderer use ROS2; no detector node, publisher, launch or output contract exists.
- Impact: the project does not yet satisfy TЗ section 3.3 items 4-5 or the required demo chain.
- Next action: implement the minimal guarded pipeline in stage 3; status under the current config must remain `UNKNOWN`.

### F3 — MEDIUM: repository status and documentation are not a frozen release

- Evidence strength: direct `git status` and documentation mismatch.
- Evidence: working tree has many staged/unstaged/untracked changes. README status says no Docker image exists, while Dockerfile and stage-1 runtime record exist.
- Impact: old evidence cannot be safely attributed to a fixed submitted version; new user may receive obsolete status.
- Next action: after the stage-3 unit and replay checks pass, create a clean reviewed checkpoint and align README status with verified facts.

## Mandatory Bug Discovery

Status: `REPRODUCED` test-infrastructure defect. See [bug audit](bug-audit-2026-09-18.md). No project files were modified.

## Smallest safe stage-3 scope

1. ROS2 node consumes configured input topic and performs the existing PointCloud2 quality gate.
2. Node loads `geometry_contract.yaml`, exposes contract status in diagnostics and publishes either a labelled assumed-geometry candidate or `UNKNOWN` when no candidate/config is unavailable.
3. Add tests for invalid geometry, malformed cloud and preservation of source frame/timestamp.
4. Do not implement numerical ROI, profile, margin, distance or cluster thresholds until their sources and test plan are approved.

## Evidence log

- Requirement inspected: `docs/hackathon_documentations/5. ДепТранспорта.pdf`, pp. 3-8: Humble/Docker, ROS bag processing, output, demo and evaluation requirements.
- Current project evidence inspected: work plan, dataset audit, stage-1/2 records, source/config/tests and Docker image metadata.
- Commands run:
  - `docker image inspect lidar-mosmetro3d:stage_2 --format '{{.Id}}'`
  - `docker run --rm lidar-mosmetro3d:stage_2 python3 -m unittest discover -s tests -v`
- Claims not verified: full stage-2 renderer rerun on the current worktree, external geometry sources, event annotation, detection performance, all six bag inputs, clean Docker build from this exact source snapshot.
- Residual risk: stage 3 cannot end in the plan's working detection baseline without external domain evidence. `UNKNOWN` is the only truthful current geometric decision.
