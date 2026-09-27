# Фильтр препятствий и модели шума

Этот документ отвечает на один практический вопрос: как текущие кандидаты модели
отработали на доступных датасетах. История экспериментов оставлена только там,
где она нужна для интерпретации чисел и соответствия ТЗ.

`candidate_baseline_v2` - это runtime-имя выбранной модели
`random_forest_lite`: 17 shallow decision trees, threshold `0.8064516129`,
портируемый C++ export без ML-библиотеки. Артефакт модели:
`models/noise_classifier_candidate_baseline_v2.json`.

## Что сейчас можно утверждать

- Таблица ниже построена **без новых запусков**, по сохранённому offline-артефакту
  `artefacts/stage_5/noise_model_candidate_hard_negative_all_sources_cal_roundT/noise_model_candidates.json`.
- Это сравнение кандидатов на одинаковом seven-source development-прогоне.
- Положительными считаются только кадры `13–64` в `doubleT_obstacle`.
  Остальные кадры считаются отрицательными по текущему рабочему допущению.
- `UNKNOWN` не считается свободным путём. В этом артефакте `FP temporal`
  включает `UNKNOWN`, поэтому для лучших моделей все оставшиеся `FP temporal`
  являются upstream/status-проблемой, а не срабатыванием ML-компонента.
- Таблица **не является проверкой текущего UI/direct player runtime**. Наблюдения
  вида `doubleT_obstacle:183` или `roundT_pressureGate_roundT:238` нужно
  фиксировать отдельным `direct_cpp`/player JSON-прогоном.

## Короткая сводка по моделям

Это итог по `model + temporal` на сохранённом seven-source development-прогоне.
`FP` включает `UNKNOWN`; ниже в документе они разобраны отдельно.

| Модель | Threshold | TP | TN | FP | FN |
|---|---:|---:|---:|---:|---:|
| `candidate_baseline_v2 / random_forest_lite` | 0.806452 | 52 | 13 514 | 193 | 0 |
| `random_forest` | 0.709677 | 52 | 13 514 | 193 | 0 |
| `lightgbm` | 0.967742 | 52 | 13 514 | 193 | 0 |
| `ensemble_v1` | 0.870968 | 52 | 13 514 | 193 | 0 |
| `gradient_boosting` | 0.967742 | 52 | 13 353 | 354 | 0 |
| `legacy_tree_v1` | 0.500000 | 52 | 13 244 | 463 | 0 |
| `decision_tree` | 0.967742 | 52 | 13 038 | 669 | 0 |
| `tree_depth3` | 0.967742 | 52 | 13 038 | 669 | 0 |
| `tree_depth5_min10` | 0.935484 | 52 | 12 453 | 1 254 | 0 |

## Вывод по сохранённому offline-прогону

Лучшая модель для текущего runtime - `candidate_baseline_v2 / random_forest_lite`.
Она не пропускает известное препятствие (`FN=0` на `doubleT_obstacle`,
кадры `13-64`), делит лучший результат по `FP temporal` с `random_forest`,
`lightgbm` и `ensemble_v1`, и уже имеет малый переносимый C++ export без
тяжёлой ML-зависимости.

По `FP temporal` при `FN=0` лучший результат делят четыре модели:
`candidate_baseline_v2 / random_forest_lite`, `random_forest`, `lightgbm`,
`ensemble_v1`. У всех `193` total FP, и все они приходят из `UNKNOWN`, а не
из срабатывания ML-компонента после temporal.

Если смотреть только offline-качество raw-сигнала, лучше всех выглядит
`lightgbm`: `193` raw FP против `201` raw FP у
`candidate_baseline_v2 / random_forest_lite`. Но `lightgbm` не выбран для
runtime, потому что его тяжелее переносить и проверять в текущем C++ пути.
Поэтому `candidate_baseline_v2 / random_forest_lite` остаётся лучшим
практическим выбором сейчас: почти не хуже по raw, равен лучшим по temporal,
`FN=0` на известном препятствии и уже подходит для runtime.

Ограничение остаётся главным: есть только один подтверждённый положительный
проезд, и он участвовал в разработке. Эти числа помогают выбрать кандидата
для текущего development baseline, но не доказывают обобщающий recall.

## Модель × датасет

`FP кадры` показывает raw-кадры; если temporal отличается, рядом указан список
`temporal`. Длинные списки обрезаны многоточием, полный список хранится в JSON.

| Модель | Режим | Датасет | TP | FN | FP raw | FP temporal | UNKNOWN | FP кадры |
|---|---|---|---:|---:|---:|---:|---:|---|
| `candidate_baseline_v2 / random_forest_lite` | offline evaluator, threshold 0.806452 | `doubleT_obstacle` | 52 | 0 | 0 | 0 | 0 | raw: - |
| `candidate_baseline_v2 / random_forest_lite` | offline evaluator, threshold 0.806452 | `doubleT_platform` | 0 | 0 | 1 | 0 | 0 | raw: 215; temporal: - |
| `candidate_baseline_v2 / random_forest_lite` | offline evaluator, threshold 0.806452 | `new_data` | 0 | 0 | 169 | 154 | 154 | raw: 94, 95, 99, 100, 101, 102, 471, 475, 484, 496, 498, 881, 1122, 1126, 1128, 1137 ...; temporal: 94, 95, 99, 100, 101, 102, 471, 475, 484, 496, 498, 881, 1122, 1126, 1128, 1137 ... |
| `candidate_baseline_v2 / random_forest_lite` | offline evaluator, threshold 0.806452 | `roundT_doubleT` | 0 | 0 | 10 | 10 | 10 | raw: 112, 113, 133, 140, 144, 146, 148, 157, 176, 180 |
| `candidate_baseline_v2 / random_forest_lite` | offline evaluator, threshold 0.806452 | `roundT_pressureGate_roundT` | 0 | 0 | 6 | 5 | 5 | raw: 133, 142, 149, 206, 253, 256; temporal: 133, 142, 149, 253, 256 |
| `candidate_baseline_v2 / random_forest_lite` | offline evaluator, threshold 0.806452 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 13 | 12 | 12 | raw: 388, 392, 405, 407, 415, 444, 452, 469, 480, 496, 512, 528, 530; temporal: 388, 392, 405, 407, 415, 444, 452, 469, 480, 496, 512, 528 |
| `candidate_baseline_v2 / random_forest_lite` | offline evaluator, threshold 0.806452 | `squareT_platform_squareT_switch` | 0 | 0 | 12 | 12 | 12 | raw: 764, 769, 780, 781, 782, 783, 784, 785, 787, 788, 789, 793 |
| `random_forest` | offline evaluator, threshold 0.709677 | `doubleT_obstacle` | 52 | 0 | 0 | 0 | 0 | raw: - |
| `random_forest` | offline evaluator, threshold 0.709677 | `doubleT_platform` | 0 | 0 | 0 | 0 | 0 | raw: - |
| `random_forest` | offline evaluator, threshold 0.709677 | `new_data` | 0 | 0 | 155 | 154 | 154 | raw: 94, 95, 99, 100, 101, 102, 471, 475, 484, 496, 498, 881, 1122, 1126, 1128, 1137 ...; temporal: 94, 95, 99, 100, 101, 102, 471, 475, 484, 496, 498, 881, 1122, 1126, 1128, 1137 ... |
| `random_forest` | offline evaluator, threshold 0.709677 | `roundT_doubleT` | 0 | 0 | 10 | 10 | 10 | raw: 112, 113, 133, 140, 144, 146, 148, 157, 176, 180 |
| `random_forest` | offline evaluator, threshold 0.709677 | `roundT_pressureGate_roundT` | 0 | 0 | 5 | 5 | 5 | raw: 133, 142, 149, 253, 256 |
| `random_forest` | offline evaluator, threshold 0.709677 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 13 | 12 | 12 | raw: 388, 392, 405, 407, 415, 444, 452, 469, 480, 496, 512, 528, 530; temporal: 388, 392, 405, 407, 415, 444, 452, 469, 480, 496, 512, 528 |
| `random_forest` | offline evaluator, threshold 0.709677 | `squareT_platform_squareT_switch` | 0 | 0 | 12 | 12 | 12 | raw: 764, 769, 780, 781, 782, 783, 784, 785, 787, 788, 789, 793 |
| `lightgbm` | offline evaluator, threshold 0.967742 | `doubleT_obstacle` | 52 | 0 | 0 | 0 | 0 | raw: - |
| `lightgbm` | offline evaluator, threshold 0.967742 | `doubleT_platform` | 0 | 0 | 0 | 0 | 0 | raw: - |
| `lightgbm` | offline evaluator, threshold 0.967742 | `new_data` | 0 | 0 | 154 | 154 | 154 | raw: 94, 95, 99, 100, 101, 102, 471, 475, 484, 496, 498, 881, 1122, 1126, 1128, 1137 ... |
| `lightgbm` | offline evaluator, threshold 0.967742 | `roundT_doubleT` | 0 | 0 | 10 | 10 | 10 | raw: 112, 113, 133, 140, 144, 146, 148, 157, 176, 180 |
| `lightgbm` | offline evaluator, threshold 0.967742 | `roundT_pressureGate_roundT` | 0 | 0 | 5 | 5 | 5 | raw: 133, 142, 149, 253, 256 |
| `lightgbm` | offline evaluator, threshold 0.967742 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 12 | 12 | 12 | raw: 388, 392, 405, 407, 415, 444, 452, 469, 480, 496, 512, 528 |
| `lightgbm` | offline evaluator, threshold 0.967742 | `squareT_platform_squareT_switch` | 0 | 0 | 12 | 12 | 12 | raw: 764, 769, 780, 781, 782, 783, 784, 785, 787, 788, 789, 793 |
| `ensemble_v1` | offline evaluator, threshold 0.870968 | `doubleT_obstacle` | 52 | 0 | 0 | 0 | 0 | raw: - |
| `ensemble_v1` | offline evaluator, threshold 0.870968 | `doubleT_platform` | 0 | 0 | 0 | 0 | 0 | raw: - |
| `ensemble_v1` | offline evaluator, threshold 0.870968 | `new_data` | 0 | 0 | 155 | 154 | 154 | raw: 94, 95, 99, 100, 101, 102, 471, 475, 484, 496, 498, 881, 1122, 1126, 1128, 1137 ...; temporal: 94, 95, 99, 100, 101, 102, 471, 475, 484, 496, 498, 881, 1122, 1126, 1128, 1137 ... |
| `ensemble_v1` | offline evaluator, threshold 0.870968 | `roundT_doubleT` | 0 | 0 | 10 | 10 | 10 | raw: 112, 113, 133, 140, 144, 146, 148, 157, 176, 180 |
| `ensemble_v1` | offline evaluator, threshold 0.870968 | `roundT_pressureGate_roundT` | 0 | 0 | 5 | 5 | 5 | raw: 133, 142, 149, 253, 256 |
| `ensemble_v1` | offline evaluator, threshold 0.870968 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 13 | 12 | 12 | raw: 388, 392, 405, 407, 415, 444, 452, 469, 480, 496, 512, 528, 530; temporal: 388, 392, 405, 407, 415, 444, 452, 469, 480, 496, 512, 528 |
| `ensemble_v1` | offline evaluator, threshold 0.870968 | `squareT_platform_squareT_switch` | 0 | 0 | 12 | 12 | 12 | raw: 764, 769, 780, 781, 782, 783, 784, 785, 787, 788, 789, 793 |
| `gradient_boosting` | offline evaluator, threshold 0.967742 | `doubleT_obstacle` | 52 | 0 | 8 | 0 | 0 | raw: 3, 5, 9, 66, 68, 70, 165, 169; temporal: - |
| `gradient_boosting` | offline evaluator, threshold 0.967742 | `doubleT_platform` | 0 | 0 | 12 | 4 | 0 | raw: 12, 35, 88, 114, 131, 132, 159, 197, 198, 215, 219, 226; temporal: 131, 132, 197, 198 |
| `gradient_boosting` | offline evaluator, threshold 0.967742 | `new_data` | 0 | 0 | 641 | 277 | 154 | raw: 4, 38, 62, 68, 74, 80, 81, 94, 95, 99, 100, 101, 102, 119, 191, 199 ...; temporal: 80, 81, 94, 95, 99, 100, 101, 102, 471, 475, 484, 496, 498, 872, 873, 875 ... |
| `gradient_boosting` | offline evaluator, threshold 0.967742 | `roundT_doubleT` | 0 | 0 | 15 | 10 | 10 | raw: 26, 34, 112, 113, 133, 140, 144, 146, 148, 155, 157, 174, 176, 180, 183; temporal: 112, 113, 133, 140, 144, 146, 148, 157, 176, 180 |
| `gradient_boosting` | offline evaluator, threshold 0.967742 | `roundT_pressureGate_roundT` | 0 | 0 | 14 | 10 | 5 | raw: 38, 133, 142, 149, 156, 163, 206, 230, 231, 232, 247, 248, 253, 256; temporal: 133, 142, 149, 230, 231, 232, 247, 248, 253, 256 |
| `gradient_boosting` | offline evaluator, threshold 0.967742 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 55 | 32 | 12 | raw: 70, 76, 146, 168, 173, 202, 214, 247, 250, 280, 283, 284, 286, 288, 293, 296 ...; temporal: 283, 284, 296, 297, 298, 299, 300, 301, 302, 303, 305, 306, 307, 308, 309, 310 ... |
| `gradient_boosting` | offline evaluator, threshold 0.967742 | `squareT_platform_squareT_switch` | 0 | 0 | 38 | 21 | 12 | raw: 37, 49, 139, 162, 168, 169, 213, 216, 218, 219, 221, 222, 223, 227, 238, 239 ...; temporal: 168, 169, 218, 219, 221, 222, 223, 238, 239, 764, 769, 780, 781, 782, 783, 784 ... |
| `legacy_tree_v1` | offline evaluator, threshold 0.500000 | `doubleT_obstacle` | 52 | 0 | 0 | 0 | 0 | raw: - |
| `legacy_tree_v1` | offline evaluator, threshold 0.500000 | `doubleT_platform` | 0 | 0 | 1 | 0 | 0 | raw: 1; temporal: - |
| `legacy_tree_v1` | offline evaluator, threshold 0.500000 | `new_data` | 0 | 0 | 528 | 369 | 154 | raw: 16, 27, 28, 29, 35, 38, 39, 45, 48, 49, 53, 55, 62, 78, 80, 81 ...; temporal: 27, 28, 29, 38, 39, 48, 49, 80, 81, 94, 95, 99, 100, 101, 102, 471 ... |
| `legacy_tree_v1` | offline evaluator, threshold 0.500000 | `roundT_doubleT` | 0 | 0 | 56 | 45 | 10 | raw: 95, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 110, 112, 113, 121, 122 ...; temporal: 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 112, 113, 121, 122, 123, 124 ... |
| `legacy_tree_v1` | offline evaluator, threshold 0.500000 | `roundT_pressureGate_roundT` | 0 | 0 | 5 | 5 | 5 | raw: 133, 142, 149, 253, 256 |
| `legacy_tree_v1` | offline evaluator, threshold 0.500000 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 34 | 25 | 12 | raw: 60, 66, 67, 122, 165, 170, 171, 172, 173, 175, 176, 177, 178, 179, 216, 388 ...; temporal: 66, 67, 170, 171, 172, 173, 175, 176, 177, 178, 179, 388, 392, 405, 407, 415 ... |
| `legacy_tree_v1` | offline evaluator, threshold 0.500000 | `squareT_platform_squareT_switch` | 0 | 0 | 26 | 19 | 12 | raw: 68, 69, 687, 705, 714, 737, 738, 739, 746, 748, 750, 751, 764, 769, 771, 775 ...; temporal: 68, 69, 737, 738, 739, 750, 751, 764, 769, 780, 781, 782, 783, 784, 785, 787 ... |
| `decision_tree` | offline evaluator, threshold 0.967742 | `doubleT_obstacle` | 52 | 0 | 12 | 0 | 0 | raw: 3, 5, 9, 66, 68, 70, 74, 94, 96, 114, 165, 169; temporal: - |
| `decision_tree` | offline evaluator, threshold 0.967742 | `doubleT_platform` | 0 | 0 | 61 | 33 | 0 | raw: 12, 35, 88, 114, 131, 132, 159, 177, 197, 198, 215, 219, 223, 224, 226, 232 ...; temporal: 131, 132, 197, 198, 223, 224, 256, 257, 258, 268, 269, 272, 273, 281, 282, 284 ... |
| `decision_tree` | offline evaluator, threshold 0.967742 | `new_data` | 0 | 0 | 1086 | 536 | 154 | raw: 4, 38, 54, 61, 62, 68, 70, 74, 80, 81, 94, 95, 99, 100, 101, 102 ...; temporal: 61, 62, 80, 81, 94, 95, 99, 100, 101, 102, 185, 186, 188, 189, 190, 191 ... |
| `decision_tree` | offline evaluator, threshold 0.967742 | `roundT_doubleT` | 0 | 0 | 22 | 13 | 10 | raw: 26, 34, 50, 68, 84, 93, 94, 95, 112, 113, 133, 140, 142, 144, 146, 148 ...; temporal: 93, 94, 95, 112, 113, 133, 140, 144, 146, 148, 157, 176, 180 |
| `decision_tree` | offline evaluator, threshold 0.967742 | `roundT_pressureGate_roundT` | 0 | 0 | 25 | 15 | 5 | raw: 38, 88, 133, 142, 149, 156, 163, 206, 212, 226, 228, 230, 231, 232, 237, 243 ...; temporal: 133, 142, 149, 230, 231, 232, 245, 246, 247, 248, 249, 250, 251, 253, 256 |
| `decision_tree` | offline evaluator, threshold 0.967742 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 78 | 41 | 12 | raw: 62, 70, 76, 102, 146, 168, 173, 191, 193, 202, 214, 247, 250, 275, 276, 277 ...; temporal: 275, 276, 277, 283, 284, 296, 297, 298, 299, 300, 301, 302, 303, 305, 306, 307 ... |
| `decision_tree` | offline evaluator, threshold 0.967742 | `squareT_platform_squareT_switch` | 0 | 0 | 59 | 31 | 12 | raw: 29, 37, 49, 84, 86, 139, 162, 168, 169, 181, 185, 187, 188, 203, 206, 209 ...; temporal: 168, 169, 187, 188, 209, 210, 218, 219, 221, 222, 223, 238, 239, 247, 248, 764 ... |
| `tree_depth3` | offline evaluator, threshold 0.967742 | `doubleT_obstacle` | 52 | 0 | 12 | 0 | 0 | raw: 3, 5, 9, 66, 68, 70, 74, 94, 96, 114, 165, 169; temporal: - |
| `tree_depth3` | offline evaluator, threshold 0.967742 | `doubleT_platform` | 0 | 0 | 61 | 33 | 0 | raw: 12, 35, 88, 114, 131, 132, 159, 177, 197, 198, 215, 219, 223, 224, 226, 232 ...; temporal: 131, 132, 197, 198, 223, 224, 256, 257, 258, 268, 269, 272, 273, 281, 282, 284 ... |
| `tree_depth3` | offline evaluator, threshold 0.967742 | `new_data` | 0 | 0 | 1086 | 536 | 154 | raw: 4, 38, 54, 61, 62, 68, 70, 74, 80, 81, 94, 95, 99, 100, 101, 102 ...; temporal: 61, 62, 80, 81, 94, 95, 99, 100, 101, 102, 185, 186, 188, 189, 190, 191 ... |
| `tree_depth3` | offline evaluator, threshold 0.967742 | `roundT_doubleT` | 0 | 0 | 22 | 13 | 10 | raw: 26, 34, 50, 68, 84, 93, 94, 95, 112, 113, 133, 140, 142, 144, 146, 148 ...; temporal: 93, 94, 95, 112, 113, 133, 140, 144, 146, 148, 157, 176, 180 |
| `tree_depth3` | offline evaluator, threshold 0.967742 | `roundT_pressureGate_roundT` | 0 | 0 | 25 | 15 | 5 | raw: 38, 88, 133, 142, 149, 156, 163, 206, 212, 226, 228, 230, 231, 232, 237, 243 ...; temporal: 133, 142, 149, 230, 231, 232, 245, 246, 247, 248, 249, 250, 251, 253, 256 |
| `tree_depth3` | offline evaluator, threshold 0.967742 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 78 | 41 | 12 | raw: 62, 70, 76, 102, 146, 168, 173, 191, 193, 202, 214, 247, 250, 275, 276, 277 ...; temporal: 275, 276, 277, 283, 284, 296, 297, 298, 299, 300, 301, 302, 303, 305, 306, 307 ... |
| `tree_depth3` | offline evaluator, threshold 0.967742 | `squareT_platform_squareT_switch` | 0 | 0 | 59 | 31 | 12 | raw: 29, 37, 49, 84, 86, 139, 162, 168, 169, 181, 185, 187, 188, 203, 206, 209 ...; temporal: 168, 169, 187, 188, 209, 210, 218, 219, 221, 222, 223, 238, 239, 247, 248, 764 ... |
| `tree_depth5_min10` | offline evaluator, threshold 0.935484 | `doubleT_obstacle` | 52 | 0 | 13 | 2 | 0 | raw: 3, 5, 9, 66, 68, 70, 74, 75, 94, 96, 114, 165, 169; temporal: 74, 75 |
| `tree_depth5_min10` | offline evaluator, threshold 0.935484 | `doubleT_platform` | 0 | 0 | 75 | 38 | 0 | raw: 12, 35, 68, 88, 105, 114, 131, 132, 159, 177, 180, 188, 192, 194, 197, 198 ...; temporal: 131, 132, 197, 198, 223, 224, 234, 235, 236, 239, 240, 256, 257, 258, 268, 269 ... |
| `tree_depth5_min10` | offline evaluator, threshold 0.935484 | `new_data` | 0 | 0 | 1804 | 1007 | 154 | raw: 2, 3, 4, 27, 38, 41, 48, 50, 51, 53, 54, 61, 62, 68, 70, 72 ...; temporal: 2, 3, 4, 50, 51, 53, 54, 61, 62, 80, 81, 94, 95, 99, 100, 101 ... |
| `tree_depth5_min10` | offline evaluator, threshold 0.935484 | `roundT_doubleT` | 0 | 0 | 34 | 21 | 10 | raw: 17, 26, 34, 50, 67, 68, 74, 84, 85, 88, 93, 94, 95, 112, 113, 133 ...; temporal: 67, 68, 84, 85, 93, 94, 95, 112, 113, 133, 140, 144, 146, 148, 157, 171 ... |
| `tree_depth5_min10` | offline evaluator, threshold 0.935484 | `roundT_pressureGate_roundT` | 0 | 0 | 47 | 33 | 5 | raw: 4, 14, 15, 17, 19, 20, 22, 38, 75, 76, 88, 133, 140, 142, 149, 156 ...; temporal: 14, 15, 19, 20, 75, 76, 133, 142, 149, 217, 218, 221, 222, 230, 231, 232 ... |
| `tree_depth5_min10` | offline evaluator, threshold 0.935484 | `roundT_squareT_pressureGate_squareT` | 0 | 0 | 129 | 68 | 12 | raw: 4, 41, 62, 70, 76, 91, 102, 139, 146, 149, 154, 164, 168, 169, 170, 171 ...; temporal: 168, 169, 170, 171, 172, 173, 187, 188, 191, 192, 193, 197, 198, 199, 200, 201 ... |
| `tree_depth5_min10` | offline evaluator, threshold 0.935484 | `squareT_platform_squareT_switch` | 0 | 0 | 123 | 85 | 12 | raw: 14, 15, 29, 36, 37, 40, 42, 49, 84, 86, 139, 145, 149, 158, 162, 167 ...; temporal: 14, 15, 36, 37, 167, 168, 169, 181, 182, 184, 185, 187, 188, 189, 190, 191 ... |

## Что не покрывает таблица

- Не проверяет текущий UI/direct-player результат.
- Не доказывает независимый recall: `doubleT_obstacle` использован в разработке.
- Не сравнивает full-path latency, очередь, dropped frames, HTTP/UI и ROS2 delivery.
- Не обновляет встроенный C++ export: замена JSON сама по себе runtime не меняет.

## Время и соответствие ТЗ

**Статус таймеров.** Дефект B01 исправлен в `src/cpp/curve_pipeline_stream_cli.cpp`: обычный stream CLI считает только активный `legacy` или `candidate_baseline_v2` фильтр; `--lean-model-benchmark` считает активную модель без wireframe/debug arrays; одновременное сравнение двух фильтров доступно только через явный диагностический флаг `--compare-noise-filters`, который использует `scripts/evaluate_noise_classifier.py`.

`common_processing_ms` теперь измеряет общий путь до noise-фильтра; `model_noise_filter_ms`/`legacy_noise_filter_ms` измеряют только выбранный фильтр; `processing_ms` - сумма общего пути и активного фильтра, а в detailed JSON также включает построение wireframe. Это всё ещё stream compute timing: ROS2 delivery, HTTP/XYZF, чтение архива, очередь/drops и отрисовка измеряются отдельно.

### Lean benchmark после замены baseline

Первые 5 минут `new_data`: 3000 кадров, диапазон 0–2999, длительность bag-времени 299,9 с. Первые две строки - исторические замеры старого одно-деревного фильтра (`UNKNOWN=29`) на image `lidar-mosmetro3d:timing-fix` и последующей spatial-index версии. Третья строка - текущий `candidate_baseline_v2` на image `lidar-mosmetro3d:candidate-baseline-v2` (`UNKNOWN=9`); результат сохранён в `artefacts/stage_5/noise_model_lean_timing_candidate_baseline_v2_new_data_5min/new_data.json`. По текущему допущению пользователя все поддержанные кадры `new_data` считаются отрицательными. `FP` и `TN` ниже - это количество кадров; `p95` - миллисекунды на один кадр.

| Запуск | FP, кадров | FP/мин | TN, кадров | Скорость обработки 95% кадров, мс/кадр | Подготовка CORE до фильтра, p95 мс/кадр | Активный фильтр для 95% кадров, мс/кадр |
|---|---:|---:|---:|---:|---:|---:|
| Historical lean C++ legacy tree | 129 | 25,8 | 2 842 | 118,5 | 47,9 | 73,8 |
| Legacy tree с voxel index для связных `CORE`-компонент | 129 | 25,8 | 2 842 | 49,8 | 47,0 | 3,8 |
| Current lean C++ `candidate_baseline_v2` | 0 | 0 | 2 991 | 51,4 | 48,4 | 4,1 |

Этот benchmark измеряет C++ stream без плеера, ROS2, HTTP, чтения архива и отрисовки. Базовая строка показывает прежний bottleneck: 95% кадров обработались за 118,5 мс или быстрее, основной вклад был в `model_noise_filter_ms`, то есть в построении/оценке компонент модели, а не в самом дереве решений как наборе порогов. После voxel index для связных `CORE`-компонент p95 старого фильтра снизился до 3,8 мс, а lean compute p95 - до 49,8 мс на том же 5-минутном окне. Текущий `candidate_baseline_v2` на этом окне даёт `0` FP и p95 активного фильтра `4,1` мс, но это всё ещё не full-path timing плеера/ROS2 с очередью и dropped frames.

### Diagnostic evaluator timing

`scripts/evaluate_noise_classifier.py` запускает stream CLI с `--compare-noise-filters` только для диагностики: на одном проходе сверить legacy и активную модель на одинаковых `CORE` компонентах. Он намеренно считает оба фильтра, поэтому его timing не является временем обычного плеера и не публикуется как active runtime benchmark.

Полный 7-source runtime-прогон после замены baseline не выполнялся: качество взято из offline candidate evaluator, а runtime проверен smoke-запуском. Для проверки совместимости выполнен one-frame smoke на `doubleT_obstacle` frame 13: `noise_filter_mode=candidate_baseline_v2`, `model_noise_filter_type=forest_lite_mean_tree_probability`, `intrusion_candidate_present=true`, `reportable_core_count=121`.

ТЗ, §8.3, не задаёт числовой предел задержки: оцениваются задержка, частота кадров, ресурсы и стабильность в реальном времени. Около 100 мс на кадр - инженерный ориентир для входа ~10 Гц, а не формальный порог ТЗ. Текущий lean stream p95 `51,4` мс на первых 5 минутах `new_data` показывает, что вычислительное C++ ядро с `candidate_baseline_v2` имеет запас относительно этого ориентира на данном окне. Однако этот замер не включает ROS2/HTTP/UI/drops и выполнялся не как чистый стендовый replay; поэтому соответствие требованиям по скорости полного решения **ещё не подтверждено**. Перед финальным выводом нужен ROS2 replay с очередью и пропущенными кадрами на целевом стенде Ubuntu 22.04 + ROS 2 Humble + Docker.

Полный offline-прогон семи записей: `artefacts/stage_5/noise_model_eval_current/*.json`. Исторический lean timing после фикса: `artefacts/stage_5/noise_model_lean_timing_timing_fix_new_data_5min/new_data.json`. Lean timing после voxel index для связных `CORE`-компонент: `artefacts/stage_5/noise_model_lean_timing_spatial_new_data_5min/new_data.json`. Текущий lean timing `candidate_baseline_v2`: `artefacts/stage_5/noise_model_lean_timing_candidate_baseline_v2_new_data_5min/new_data.json`. Исходный исторический отчёт сохранён в [stage_5_noise_model_all_datasets_eval.md](stages/stage_5/stage_5_noise_model_all_datasets_eval.md).

## Следующие проверки

1. Для расхождений со скриншотами сохранить `direct_cpp`/player JSON по конкретным кадрам и сравнить его с offline evaluator.
2. После обучения на синтетике сравнить новую модель с `candidate_baseline_v2` на одинаковых split, threshold, temporal-policy и runtime-export правилах.
3. Перед финальной сдачей выполнить чистый запуск Ubuntu 22.04 + ROS 2 Humble + Docker и full-path replay с очередью, dropped frames и ресурсами.


