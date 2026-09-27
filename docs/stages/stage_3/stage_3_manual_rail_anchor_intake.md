# Intake ручных anchors рельсов, кадр 168

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 3, режим `validation`/documentation.

## Задача

- Goal: сохранить пользовательские четыре source-точки рельсов как ограниченный development-артефакт и проверить их identity/присутствие в исходном облаке.
- Наблюдаемая проблема: текущая разметка не даёт достаточно согласованных пар для заявления straight-axis калибровкой, но пользователь явно просит продолжать с доступными данными.
- Non-goals: менять active envelope, margin, YAML, детектор, ROS2-интерфейсы, thresholds, карту, ground/rail suppression либо статус безопасности.
- Source of truth: экспорт пользователя `C:/Users/Ilya/Downloads/live_envelope_frame_168 (3).json`; manifest и xyzf кадра 168; `docs/README_methodology.md`; `config/geometry_contract.yaml`.
- Пункт/этап плана: этап 3 — development проверка геометрической гипотезы; не evidence сквозного baseline.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker. Фактическая проверка: Windows workspace, read-only Node.js проверка экспортированного player-артефакта.
- Вход: `doubleT_obstacle`, кадр 168, `lidar_livox`, source XYZ без преобразования; единицы — `m_ASSUMED`.
- Рабочий frame/transform: `source_frame = lidar_livox`; transform не применяется, то есть identity `source <- source`.
- Временная база: header timestamp используется только для identity; задержка не измерялась.
- Allowed files: этот отчёт и `artefacts/stage_3/manual_rail_reviews/rail_anchors_frame_168.json`.
- Files to avoid: detector/runtime config, geometry contract, annotations evaluator, raw data/export и ROS2-пакеты.
- Защищённые контракты: `UNKNOWN != CLEAR`; raw XYZ неизменён; source frame/identity явны; ручная разметка не является калибровкой или safety decision.
- Deliverables: сохранённый development artifact — implemented; проверка принадлежности source cloud — implemented; активное применение — not implemented.
- Основной агент: `lidar_obstacle_pipeline`; safety-проход выполнен текущим агентом, так как артефакт описывает ручную геометрию. Отдельный `validation_reviewer` не запускался: детектор и метрики не менялись.
- Validation target: L0 для нового артефакта; проверка source identity, не runtime/физическая валидация.
- Stop conditions: не объявлять прямую ось, габарит, рельсовую колею, расстояния или решение о безопасности проверенными.

## Что изменено

Добавлен [development-артефакт ручной разметки](../../../artefacts/stage_3/manual_rail_reviews/rail_anchors_frame_168.json). Он сохраняет четыре anchors, identity кадра и вычисленную midpoint-ось только для визуального review. Артефакт не подключён ни к одной активной конфигурации или вычислению детектора.

## Evidence и выполненная проверка

Изучены экспорт live-envelope, manifest и `frame_00168.xyzf`. Выполнена read-only команда:

```text
node -e "... exact source XYZ match ..."
```

Результат: identity совпадает с manifest (`frame_index=168`, header `946687314399992943`, `lidar_livox`); каждая из четырёх anchors совпала с двумя source-возвратами при tolerance `1e-6`.

Проверка геометрии пар: длины 1.867 и 1.772 м* (разница 0.095 м*), угол направлений пар 45.890°. Следовательно, ручная straight-axis гипотеза на 43.182 м* остаётся `UNVERIFIED_CURVATURE_OR_PICK_ERROR`; это не измерение физической колеи.

## Safety-проход

`PASS_WITH_RISKS` только для сохранения development evidence: raw облако и активные настройки не изменены, артефакт явно запрещает использовать себя для `CLEAR`, suppression, active envelope или калибровочного claim. Угол пар не скрыт и не нормализован.

## Validation level и остаточный риск

L0: подтверждена структурная целостность/identity и наличие anchors в source cloud. Не проверены физический смысл выбранных головок рельсов, оси/единицы, прямизна пути, калибровка, runtime или качество обнаружения. Остаточный риск: проекция midpoint-сегмента через возможную кривизну пути создаст неверный габарит; поэтому артефакт изолирован от active pipeline.

Следующий минимальный тест: добавить отдельный read-only viewer/import preview, который покажет эту ось только на кадре 168 и явно сохранит `UNKNOWN` за её пределами; перед реализацией потребуется отдельный план и проверка safety-границ.
