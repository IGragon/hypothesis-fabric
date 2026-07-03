# Spec: Orchestrator / state machine (M4) — Вариант 2

> Стейт-машина: переходы стадий + LLM-слоты + context budget. Ссылается на
> `03-component.md` (#1–#4), `04-workflow.md`.

## Роль
Детерминированно проводить run по стадиям: KPI parse → retrieve → generate →
score → explain → export. LLM вызывается в слотах; переходы — правила.

## Шаги / правила переходов / stop condition

| Стадия | Переход | Тип | Требование |
|--------|---------|-----|------------|
| KPI/Task Parser | → retrieve | deterministic | [R-IN1][R-IN2][ASSUM-4] |
| Retrieve | → generate (если evidence enough) | det.+LLM | [R-F1][R-F7] |
| Generate | → citation_bind (если valid) | `LLM/Agent` slot | [R-F6][R-OUT4] |
| Citation Bind | → score | deterministic | [R-F9] |
| Score | → constraint_check | det.+LLM | [R-F7][R-OUT5..7] |
| Constraint | ok → explain; violation → FE4 → generate | deterministic | [R-IN2] |
| Explain | → export | `LLM/Agent` slot | [R-F8][R-F10] |
| Export | → end | deterministic | [R-F12][R-F13] |

**Stop conditions**: достижение Export; stage timeout (FE5); hard-ограничение
без альтернатив (FE4 → end with status).

## Retry / fallback
- FE1: evidence недостаточно → расширить запрос (cap 2).
- FE2: candidates invalid → re-prompt (cap 3).
- FE4: нарушение → отбраковать → вернуться в Generate.
- FE5: stage timeout → partial + `incomplete`.

## Context handling
- Context Budget Enforcer (#2): каждый слот получает truncate/rerank evidence до
  16k токенов [R-N4].
- Canvas: transition rules (#3) поддерживают re-run стадии по правке артефакта
  [R-F14].

## Требования
[R-F1][R-F6][R-F7][R-F8][R-F9][R-F12][R-IN1][R-IN2][R-N1][R-N4][R-F14][ASSUM-4]
