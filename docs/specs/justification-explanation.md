# Spec: Justification & Explanation (M7) — Вариант 2

> Обоснование (LLM-слот) + привязка цитат + граф + неопределённость (det.).
> Ссылается на `03-component.md`, `04-workflow.md` (стадии Citation Bind, Explain).

## Роль
Для каждой гипотезы: текстовое обоснование [R-F8], привязка к источникам
[R-F9][R-K2], визуализация связей [R-F10], оценка неопределённости и
рекомендации по верификации [R-F11].

## Citation Bind (deterministic)
- Жёсткий мэтч claim→source_id из VectorDB/KG.
- Coverage gate ≥ 85%; иначе FE6 (re-generate, cap 2) [R-K2][R-F9].
- Hallucination-source rate ≤ 4% [R-K2].

## Explain slot (LLM/Agent)
- Обоснование: claim → evidence → mechanism → uncertainty → verification_plan.
- Механизм влияния [R-OUT4]; аналогии/контрфактуалы [R-F6]; язык запроса [R-N2].
- Оценка неопределённости (low/med/high) + рекомендации по верификации [R-F11].

## Визуализация (deterministic)
- Рендер графа связей гипотезы из KG/Storage [R-F10].

## Failure modes
- FE6: cite_bind low coverage → re-generate с требованием источника, cap 2.
- FE7: конфликт источников → отметить, выбрать надёжный, зафиксировать альтернативу [R-N3].

## Требования
[R-F6][R-F8][R-F9][R-F10][R-F11][R-OUT4][R-K2][R-N2][R-N3]
