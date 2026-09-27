# Импорт ручной разметки рельсов

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: загружать экспорт `lidar-manual-review-v1` в Stage 2 player и применять
  ручную ось только к точно совпадающему датасету, кадру, header timestamp и
  source frame. Это позволит визуально показать габарит на отрезке между
  размеченными сечениями (для приложенного файла — около 33.20 м).
- Наблюдаемая проблема: экспорт ручных четырёх точек нельзя восстановить после
  перезагрузки, хотя текущий player уже умеет строить отрезок между ними.
- Non-goals: не менять профиль поезда, margins, detector, status `UNKNOWN`,
  ROS2, TF, данные или сохранённые Stage 3 результаты; не экстраполировать
  габарит за дальнее сечение.
- Source of truth: экспорт пользователя `lidar-manual-review-v1`, manifest
  текущего плеера и исходный XYZ frame. Файл экспорта прямо запрещает safety
  decision (`safety_decision_permitted: false`).
- Этап: Stage 2, visual review.
- Вход/единицы: `SOURCE_XYZ_UNCHANGED`, `m_ASSUMED`; рабочий frame совпадает с
  source frame, transform отсутствует (identity).
- Allowed files: `web/stage_2_raw_player.html`, `web/stage_2_review_layers.js`,
  `tests/test_review_layers.cjs`, этот документ и служебные served copies.
- Files to avoid: detector/config YAML, данные, ROS2-контракты и thresholds.
- Защищённые контракты: ручная ось ограничена одним кадром и отрезком между
  парами; несовпадение identity ведёт к отказу импорта, а не к применению;
  за пределами отрезка остаётся `UNKNOWN`.
- Deliverable: кнопка импорта и диагностируемая проверка identity; статус —
  planned.
- Основной агент: `lidar_obstacle_pipeline`.
- Reviewer: `safety_geometry_reviewer`, так как затрагивается источник
  визуальной оси/envelope.
- Validation: L1 target — unit test identity/границы плюс browser smoke на
  `doubleT_obstacle`; L2 не заявляется до отдельной проверки геометрии.
- Acceptance: валидный экспорт для текущего кадра восстанавливает четыре
  anchors; неверный dataset/frame/header/source frame отвергается; outside
  segment остаётся UNKNOWN; исходной XYZ не изменяется.
- Stop conditions: нет подтверждённого соответствия входному кадру, попытка
  активировать safety decision или экстраполировать за anchors.

## Отчёт о завершении

### Что изменено

- Добавлена кнопка `Импорт оси JSON` и локальный выбор файла.
- Импорт принимается только для `lidar-manual-review-v1` с неизменёнными
  source XYZ, единицами `m_ASSUMED`, запрещённым safety decision и моделью
  двух пар рельсов.
- Перед применением проверяются dataset, первый header timestamp, индекс
  кадра, header timestamp кадра и source frame. Несовпадение отклоняется.
- Восстанавливаются только четыре rail anchors. Габарит остаётся отрезком
  между ними; сохранённые Stage 3 результаты не пересчитываются.

### Evidence inspected

- Пользовательский экспорт: один record для `doubleT_obstacle`, frame 0,
  `lidar_livox`; четыре координаты совпали с raw XYZ frame 0.
- Средние пар задают ось длиной 33.20 м. Расхождение измеренной ширины пар
  0.293 м не считается калибровкой и не снимает visual-only ограничение.
- Код `classifyLocal` и `crop` ограничивают поддержанный интервал `0…axis.length`.

### Commands run

- `node --test tests/test_review_layers.cjs tests/test_player_layout.cjs tests/test_player_playback.cjs tests/test_raw_player.cjs` — 16/16 PASS.
- Browser smoke на `doubleT_obstacle`, frame 0: кнопка импорта присутствует;
  исходное облако загружено без преобразования.

### Safety-review

`PASS_WITH_RISKS` для visual-only импорта. Проверено: frame identity не
подменяется, `safety_decision_permitted` остаётся false, габарит не
экстраполируется, а точки вне сегмента классифицируются `UNKNOWN`. Не
проверены: физическая точность четырёх кликов, ширина колеи, поперечный
уклон и пригодность к safety decision.

### Validation-review

`PASS_WITH_RISKS`, L1. Узкий тест проверяет успешный импорт и отказы для
другого dataset, другого frame identity и safety-разрешённого файла; браузер
подтверждает наличие элемента управления. End-to-end загрузка конкретного
пользовательского файла после обновления страницы ещё должна быть выполнена
в плеере.

### Residual risk и следующий шаг

Импортировать файл на кадре 0 через кнопку, затем визуально проверить
прохождение оси и габарита по рельсам на всём 33.20-метровом отрезке. Не
использовать результаты как `CLEAR` или safety decision.
