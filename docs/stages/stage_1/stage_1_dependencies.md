# Этап 1 — манифест зависимостей Python

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Спецификация

- Goal: сопоставить импорты `src/` и `scripts/` с `requirements.txt`, не меняя ROS 2-контракты или Docker-окружение.
- Наблюдаемая проблема: `requirements.txt` содержал только комментарии, хотя код напрямую использует NumPy и Matplotlib.
- Non-goals: реализация детектора, изменение геометрии, заменa APT на pip, добавление ML-зависимостей.
- Source of truth: ТЗ §3.2–3.3, `docs/methodology.md` §§4 и 18, этап 1 `docs/work_plan.md`, Dockerfile и фактические импорты.
- Пункт ТЗ и обязательный результат: Ubuntu 22.04 + ROS 2 Humble + Docker; все дополнительные зависимости устанавливаются автоматически при сборке образа.
- Этап: 1, «Чтение данных и запуск».
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка — Windows с локальным Python 3.10 virtualenv.
- Входные данные, frames и временные контракты: не применимо; они не меняются.
- Allowed files: `requirements.txt`, этот отчёт.
- Files to avoid: `Dockerfile`, `src/`, `scripts/`, ROS-сообщения, QoS, конфигурация геометрии и данные.
- Защищённые контракты: ROS 2 Humble и установка ROS-пакетов через базовый образ/Apt остаются без изменений.
- Deliverable: явный pip-манифест NumPy и Matplotlib; статус `implemented`.
- Основной проход: текущий агент по `agents/lidar_obstacle_pipeline.md`.
- Отдельный validation-проход: выполнен текущим агентом по `agents/validation_reviewer.md`; независимым review не является.
- Safety-review: не нужен — изменения не затрагивают координаты, envelope, пороги или временную политику.
- Validation target: L1 для статической согласованности манифеста и чистых функций.
- Validation method: проверить фактические импорты, `pip check`, компиляцию Python и unit-тесты чистых функций.
- Acceptance criteria: в `requirements.txt` перечислены ровно внешние pip-зависимости кода; ROS 2-пакеты явно остаются в Docker/Apt.
- Stop conditions: не добавлять зависимости без прямого импорта или подтверждённой необходимости; не подменять ROS-пакеты pip-пакетами.

## Отчёт о завершении

- Что изменено: NumPy и Matplotlib внесены в `requirements.txt`; добавлено пояснение границы между pip-зависимостями и пакетами ROS 2/Apt.
- Evidence inspected: ТЗ §3.2–3.3, `docs/methodology.md`, `docs/work_plan.md`, Dockerfile, все Python-файлы в `src/` и `scripts/`.
- Commands run: `pip check` в локальном virtualenv — `No broken requirements found`; bundled Python выполнил `unittest discover -s tests -v` с `PYTHONPATH=src` — 9/9 passed; `py_compile` всех Python-файлов в `src/` и `scripts/` — exit 0. Сканирование импортов нашло только NumPy и Matplotlib среди внешних pip-зависимостей. Затем выполнены `docker build --progress plain -t lidar-mosmetro3d:stage_1 .` и `scripts/validate_stage_1.ps1`: в Ubuntu 22.04.5/Humble найдены NumPy 1.21.5 и Matplotlib 3.5.1, тесты 9/9; offline audit и ROS replay получили 252/252 для `roundT_doubleT`, 201/201 для `doubleT_obstacle` и 252/252 при альтернативном пути bag, без ошибок.
- Validation level achieved: L1 для манифеста и контейнерного входного сценария. Это не L3 baseline/детектора и не claim о real-time: измерены только callback и offline-audit, без детектора и DDS queue latency.
- Что не проверено: зависимости в `requirements.txt` не устанавливаются Dockerfile через pip — целевой образ намеренно использует эквивалентные пакеты Ubuntu/Apt. Геометрия, envelope, детектор и метрики обнаружения не реализованы и не проверялись.
- Residual risk: верхние границы версий не зафиксированы; воспроизводимый образ закреплён дистрибутивными пакетами Ubuntu 22.04 в Dockerfile.
- Следующий минимальный тест: при следующем изменении Dockerfile выполнить чистую сборку и `scripts/validate_stage_1.ps1`.
