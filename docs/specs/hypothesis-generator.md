# Spec: Hypothesis Generator (M5) — Вариант 2

> LLM-слот генерации гипотез + выявления пробелов. Ссылается на
> `03-component.md` (#9, #10), `04-workflow.md` (стадия Generate).

## Роль
Из retrieved evidence и ограничений генерировать кандидаты гипотез (аналогии,
контрфактуалы, предсказания) [R-F6][R-OUT4]; выявлять пробелы в знаниях [R-F5].

## Входы / выходы

| Направление | Данные | Требование |
|-------------|--------|------------|
| Вход | ranked evidence (M2) + цель/ограничения + KG-контекст | [R-IN1..3][R-F4] |
| Выход | candidates[] (claim + mechanism + expected effect) | [R-OUT4][R-F6] |

## Слоты

| Слот | Тип | Роль | Требование |
|------|-----|------|------------|
| Candidate Synthesizer | `LLM/Agent` | гипотезы из evidence по аналогиям/контрфактуалам | [R-F6] |
| Novelty Gap Finder | `LLM/Agent` | пробелы в KG → гипотезы-предположения | [R-F5] |

## Ограничения
- Context budget ≤ 16k токенов/слот (Enforcer) [R-N4].
- Timeout 15s; schema-validation выхода; FE2: re-prompt cap 3.
- Выход на языке запроса [R-N2].

## Failure modes
- FE2: candidates invalid → re-prompt со строже схемой, cap 3.
- FE4: constraint_check отбраковал → возврат в Generate (по решению M4).

## Требования
[R-F5][R-F6][R-OUT4][R-N2][R-N4][R-N1]
