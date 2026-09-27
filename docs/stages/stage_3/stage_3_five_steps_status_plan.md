# Проверка реализации пяти шагов

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим inspect/validation, этап 3.

- Цель: проверить CurveRailAxis, sweep профиля, пересечения, предупреждения/расстояние на видео, оценку и сквозную сдачу по текущему коду и evidence.
- Источники: docs/README_work_plan.md, спецификация CurveRailAxis, web-модули и их тесты, каталог new_data, скрипты replay/видео/метрик, результаты запусков. Требования ТЗ не пересматриваются.
- Вход: существующее development-окно new_data 1050–1150 и synthetic tests; исходные XYZ и временная база не меняются. Геометрия остаётся ASSUMED в hesai_lidar, target <- source не изменяется.
- Non-goals: исправления кода, новая калибровка, изменение конфигураций/тестов, полный bag replay, сборка Docker, сертификация.
- Allowed files: этот план, отдельный stage_3_five_steps_status_run.md, новые артефакты проверки в artefacts/stage_3/five_steps_status/.
- Контракты: профиль, margin, пороги, raw, TF и часы неизменны; UNKNOWN не равен CLEAR; обнаружение кандидатов не доказывает качество.
- Основной агент и validation: текущий агент, отдельный проход доказательств без заявления независимости. Safety-review изменения не требуется: алгоритм не редактируется.
- Цель валидации: L1 для существующих узких Node-тестов и bounded offline replay; L0 для остальных компонентов. Среда проверки Windows/Node; целевая среда сдачи Ubuntu 22.04/Humble/Docker.
- Команды: node --test tests/test_live_envelope.cjs tests/test_review_layers.cjs tests/test_player_playback.cjs tests/test_auto_rails.cjs; node scripts/replay_new_data_visual.cjs artefacts/stage_3/new_data_transfer/baseline_1050_1150 artefacts/stage_3/five_steps_status; rg/Get-Content по связанным файлам.
- Acceptance: каждому шагу присвоен статус с пределами доказательств; исторические результаты не названы текущими; непокрытые реальные сценарии названы.
- Stop: недоступный вход или упавший тест фиксируются без расширения задачи до исправления.
- Отчёт: docs/stages/stage_3/stage_3_five_steps_status_run.md; следующий минимальный тест определяется по результатам.
