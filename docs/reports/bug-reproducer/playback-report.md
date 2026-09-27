# Bug Reproducer

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Исторический отчёт/исследование; команды, режим и результаты относятся к описанной ниже проверке, не ко всей текущей версии.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## ✅ FIX_PROVEN — Bug reproduced and fix proven

> Два детерминированных воспроизводителя red -> green; соседний набор 26/26. Утверждение ограничено crop/lifecycle, не частотой WebGL.

**Project:** lidar_MosMetro3D
**Bug:** Сброс crop и пустая сцена при воспроизведении
**Environment:** Windows, Node.js v24.19.0; in-app Chromium; существующий Docker HTTP server :8080.
**Generated:** 2026-09-20

## Original report

При запуске воспроизведения пропадает опция «Показывать внутри габарита с отступами», изображение дёргается.

| Contract | Expected | Actual |
|---|---|---|
| Observed behavior | Preference сохраняется; до готовности следующего кадра виден предыдущий со своим номером; новая геометрия не заимствуется из старого кадра. | setFrame снимал checked; showFrame вызывал unload/removeCloud до await fetch. |

## Minimal reproduction

Настоящий createReviewLayers на двух синтетических осях; настоящий inline player с контролируемым fetch и заглушками WebGL/OrbitControls. Контроль подтверждает успешную загрузку нового кадра.

**Confirming signal:** crop.checked false вместо true; raw-frame отсутствует во время незавершённого fetch.

### Reproduction files approved at Gate 1

- [test_player_playback.cjs](../../../tests/test_player_playback.cjs) (строка 1 в исторической версии) — Gate 1: согласованный воспроизводитель.

## Red to green evidence

| Evidence | Before fix | After fix |
|---|---:|---:|
| Exit code | 1 | 0 |
| Timed out | False | False |
| Duration | — ms | 244.539 ms |
| Same command | — | True |
| Broader suite | — | passed |

### Before — failing evidence

```text
✖ crop preference survives frame changes; crop uses the new axis, never the previous one (4.3381ms)
✖ playback retains the displayed cloud while the next frame response is pending (4.3688ms)
✔ playback harness reaches next-frame commit with exactly one source cloud and matching identity (2.9328ms)
ℹ tests 3
ℹ pass 1
ℹ fail 2
ℹ duration_ms 90.6826
AssertionError: changing frame must not reset the user crop preference
AssertionError: pending frame I/O must not expose an empty scene
```

### After — fixed evidence

```text
✔ crop preference survives frame changes; crop uses the new axis, never the previous one (4.2947ms)
✔ playback retains the displayed cloud while the next frame response is pending (3.8084ms)
✔ playback harness reaches next-frame commit with exactly one source cloud and matching identity (1.7361ms)
ℹ tests 3
ℹ suites 0
ℹ pass 3
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 93.9468
```

## Root cause

Безусловный сброс crop в setFrame и преждевременное удаление отображаемого облака перед сетевым ожиданием. Меняющаяся высота сообщений могла дополнительно изменять viewport.

## Approved fix

Сохранена preference; crop применяется только к текущему envelope. Старый кадр удерживается до decode; unload/replace/setFrame выполняются без await. Загрузка/ошибка вынесены в overlay, размеры динамических статусов зафиксированы; версия JS обновлена.

**Why this is causal:** Убраны обе операции, на которых падают воспроизводители. Новая ось и raw обновляются вместе; UNKNOWN сохраняет все точки.

### Production files approved at Gate 2

- [stage_2_raw_player.html](../../../web/stage_2_raw_player.html) (строка 177 в исторической версии) — Gate 2: удержание кадра и стабильный viewport.
- [stage_2_review_layers.js](../../../web/stage_2_review_layers.js) (строка 329 в исторической версии) — Gate 2: сохранение пользовательского фильтра.
- [test_live_envelope.cjs](../../../tests/test_live_envelope.cjs) (строка 100 в исторической версии) — Согласованное изменение прежнего ожидания reset.

## Verification

| Check | Status | Evidence |
|---|---|---|
| Узкие тесты | ✅ passed | До: 2 fail, 1 pass; после: 3/3 pass. |
| Соседние тесты | ✅ passed | 26/26, включая raw identity, новые оси, UNKNOWN и низкие точки. |
| Браузер | ✅ passed | Play от 0 до 111, crop включён; одинаковые scene rect на 1/39/111; видимое облако при loading. |

## Reproduce

```bash
node --test tests/test_player_playback.cjs
```
```bash
node --test tests/test_player_playback.cjs tests/test_live_envelope.cjs tests/test_auto_rails.cjs tests/test_review_layers.cjs tests/test_raw_player.cjs
```

## Limitations

- L1 для воспроизводителей + browser smoke одного development-проезда; не сертификация, не общая гарантия плавности.
- Исходное MP4 не просмотрено: браузер блокирует file URL; симптом проверен отдельным воспроизводителем.
- Граница поддержанного участка может меняться между реальными кадрами; её не сглаживали и не экстраполировали.
- При открытых инструментах на небольшом viewport страница прокручивается; размеры сцены стабильны.

## Residual risks

- Частота кадров по-прежнему зависит от fetch/вычислений/GPU; планировщик скорости не переработан.
- Во время ожидания виден предыдущий кадр с явной подписью. Это replay UI, не realtime safety output.

## Notes

- Gate 2 подтверждён пользователем «да» перед исправлением.
- Только согласованные runtime-файлы; XYZ, manifest, геометрические параметры и launcher не изменялись.
- Первый запуск launcher упёрся в sandbox Docker config; разрешённый повтор переиспользовал сервер без Docker build.
- Дальностной эксперимент отделён: docs/stages/stage_5/stage_5_range_200_feasibility.md.

---

Generated by `$bug-reproducer`. A fix is proven only by the same red-to-green reproducer plus relevant broader checks.
