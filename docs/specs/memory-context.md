# Spec: Memory & Context (M8) — Вариант 2

> Session store, canvas, context budget, labels. Ссылается на
> `03-component.md` (#14, #15), `05-dataflow.md` (узлы 11, 12).

## Роль
Управлять состоянием run, контекстом слотов и долгосрочными labels фидбэка.
Не дообучает LLM [ASSUM-7].

## Session state
- Состояние стадий + артефакты каждой стадии; персистентно [R-F14].
- Canvas: редактируемые артефакты, re-run стадии без потери [R-F14][R-A2].

## Memory policy

| Ресурс | Область | Политика | TTL | Требования |
|--------|---------|----------|-----|------------|
| Session Store | run | артефакты стадий, состояние | run | [R-F14] |
| Feedback Labels | долгосрочная | accepted/rejected/adjusted; калибровка весов | бессрочно (удаление по запросу) | [R-A3] |
| Context budget | слот | ≤ 16k токенов; Enforcer truncate/rerank | слот | [R-N4] |

## Feedback-интеграция
- Expert Feedback Loop (M10) пишет labels; Weighted Ranker (M6) калибруется по
  ним [R-A3].
- Конфликт labels от разных экспертов → хранить оба, отмечать конфликт.

## Конфиденциальность
- Вся память on-prem; redaction в логах [R-N5].

## Требования
[R-F14][R-A2][R-A3][R-N4][R-N5][ASSUM-7]
