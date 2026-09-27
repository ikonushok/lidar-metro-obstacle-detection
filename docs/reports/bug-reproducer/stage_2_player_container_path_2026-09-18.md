# Исправление пути Stage 3 для player — 2026-09-18

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Исторический отчёт/исследование; команды, режим и результаты относятся к описанной ниже проверке, не ко всей текущей версии.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Цель: устранить сбой подготовки player при передаче файла Stage 3 в Docker.

Категория: bug-reproducer; относится к Stage 2/3.

## Наблюдаемое поведение и первопричина

`scripts/run_stage_2_player.ps1 -RebuildData` передавал в контейнер путь
`/stage3/overlay_replay\stage_3_results.jsonl`, который в Linux не существует.
Относительная часть была получена из Windows-пути и сохраняла обратный слеш.

## Изменение

В `scripts/run_stage_2_player.ps1` после удаления начального разделителя добавлена
замена `\` на `/` только для `$stage3ResultsRelative`. Пути хоста в Docker mount
не меняются.

## Выполненные проверки

1. До изменения: `docker run --rm lidar-mosmetro3d:stage_3_baseline python3 -m unittest tests.test_run_stage_2_player_path -v` — RED, тест подтвердил отсутствие нормализации.
2. После изменения: та же команда — GREEN, 1/1.
3. `docker run --rm lidar-mosmetro3d:stage_3_baseline python3 -m unittest discover -s tests -v` — 30/30 успешно.
4. PowerShell parse `scripts/run_stage_2_player.ps1` — успешно.

## Уровень валидации и границы

L1: статическая и контейнерная unit-проверка изменённого пути.
Повторный end-to-end запуск `run_stage_2_player.ps1 -RebuildData` с реальными
данными ещё не выполнен; он остаётся следующим минимальным тестом. Отдельная
проверка `Path.is_file()` в контейнере не была запущена, так как запрос на неё
был отклонён.

Остаточный риск: исправление не доказывает работу всего player-пайплайна, но
устраняет именно переданный в ошибке POSIX-путь.
