# Ревизия документации и плана — 2026-09-23

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированный аудит/его task spec до редакции D0–D3. Исходный реестр/SHA сохранён; актуальные изменения перечислены в отчёте D0–D3.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

- Режим: inspect / docs-vs-code / validation.
- Цель: сопоставить все проектные Markdown-файлы с текущими кодом, конфигурациями и планом; отделить сделанное, расширения плана и незавершённые обязательства.
- Этап: сквозная ревизия этапов 1–8, учёт текущих экспериментов этапа 5.
- Источники: ТЗ `docs/hackathon_documentations/5. ДепТранспорта.pdf`, исходники, конфигурации, тесты; актуальные `docs/README_work_plan.md`, `docs/README_methodology.md`, `docs/README_dataset_audit.md` как проверяемые утверждения.
- Non-goals: изменение алгоритмов, порогов, геометрии, зависимостей, тестов и исторических результатов; повторный полный replay датасета.
- Среда аудита: Windows / PowerShell; целевая среда продукта — Ubuntu 22.04 + ROS 2 Humble + Docker.
- Данные: инвентаризация и доступные артефакты; новые метрики качества по облакам не вычисляются. Frames, transforms, часы и split не меняются.
- Разрешённые записи: этот task spec; `docs/reports/project-readiness/lidar-mosmetro3d-documentation-2026-09-23/`; сырые результаты `artefacts/documentation_revision_20260923/`.
- Основной исполнитель: текущий агент, без субагентов. После анализа — отдельный проход по `agents/validation_reviewer.md`; независимость review не заявляется. Safety-review не нужен: геометрия и её контракты не меняются.
- Защищённые контракты: все перечисленные в AGENTS.md сохраняются.
- Deliverables: индекс, code-only report, docs-vs-code report, bug-candidate report, полный реестр Markdown с индивидуальным статусом и предложенный порядок работ.
- Validation target: статическое сопоставление L0; L1 только для фактически выполненных существующих узких тестов. Новая проверка ROS/Docker и L3–L5 не подразумеваются.
- Метод: git status с локальным safe.directory, инвентаризация rg, чтение исходников и документов, проверка локальных ссылок, доступные существующие тесты без установки зависимостей.
- Acceptance: охват каждого проектного Markdown зафиксирован; выводы имеют первичные code/config evidence; исторический отчёт не выдаётся за текущую реализацию; пробелы в evidence названы.
- Прежние аудиты читаются только после фиксации новых выводов из первичных источников; используются как проверяемые документы, а не основание нового аудита.
- Stop conditions: недоступные runtime/dependencies отмечаются как непроверенные; нет установки, исправлений кода или воспроизводящих файлов без отдельного запроса.
- Исходное рабочее дерево: два untracked файла `stage_5_curve_limited_horizon.md` и `stage_5_curve_limited_horizon_run.md`; сохраняются без изменений.

## Отчёт о завершении

- Созданы 6 связанных отчётов: index, code-only, docs-vs-code, bug-audit, реестр 124 исходных MD и предложение очереди работ. [Результат ревизии](../../reports/project-readiness/lidar-mosmetro3d-documentation-2026-09-23/index.md).
- Изучены первичные src/scripts/config/web/tests, Dockerfile, требования PDF, active docs; historical stage/task/audit MD просмотрены по ключевым claims и ограничениям. Все исторические эксперименты не воспроизводились.
- Команды: rg inventory/contract/import searches, Get-Content, git status/diff/diff --check; pypdf extraction с UTF-8; version/import check .venv; существующие Node и Python suites; JSON aggregation и file-link checks.
- Результаты: Node 58/58 PASS; Python 75 items, 71 OK, 4 ERROR (три HTTP ConnectionRefused, один rclpy import). Saved summaries: 13 759 кадров, UNKNOWN 193, legacy/model negative alarms 4 797/457. Это проверка сохранённых counters, не новый replay.
- Локальная пользовательская .venv: Python 3.12.10, запуск подтверждён; .python-version=3.10 относится к целевой подготовке Humble. ТЗ не требует смены Windows .venv; окружение не менялось.
- Отдельный validation-проход текущим агентом: code contradictions отделены от кандидатов; history не названа текущим failure; old metrics не перенесены на изменённый C++; independent safety review не заявлялся.
- Уровень: L1 для локальных tests, L0 для статического аудита. Docker API недоступен из sandbox; новый build/ROS/CUDA replay не выполнялся.
- Во время ревизии сторонняя задача изменила tangent implementation в curve_envelope_core.cpp и соответствующий C++ test; изменения просмотрены, но не выполнялись этим агентом и не получили нового runtime PASS.
- Остаточный риск: physical geometry/labels, разные default inference paths, ошибка current timing, неполная связь historical evidence с revision. Следующий шаг: актуализировать runtime/signal contract и timing, затем одинаковые контрольные случаи через выбранный ROS2 runtime и viewer.
