# Spec: Knowledge Graph Service (M3) — Вариант 2

> KG — первый класс; предbuilt детерминированно. Ссылается на
> `02-container.md` (Container 6), `03-component.md` (#7).

## Роль
Хранить сущности/связи с provenance; поддерживать выявление пробелов [R-F5] и
оценку новизны через граф-дистанцию [R-OUT5]. Фиксировать конфликты источников.

## Модель данных
- Узлы: Material, Parameter, Property, Process, Source [R-F4].
- Рёбра: influences, measured_as, composed_of, contradicts [R-N3].
- Provenance на рёбрах (источник/дата/условия) [R-F3].

## Построение
- Извлечение при ETL (M1); LLM-рефинмент сущностей (`LLM/Agent` slot) +
  детерминированное связывание provenance [R-F4].

## Запросы
- kg_traverse: Cypher/SPARQL, параметризованный (защита от инъекций) [R-F4].

## Расширяемость
- Новые домены (полимеры/композиты) — расширение схемы узлов/рёбер без перестройки
  ядра [R-K4][AD-10].

## Failure modes
- FE7: конфликт источников → ребро `contradicts`; explain-слот отмечает [R-N3].
- FE9: рассинхрон KG и индекса → пересчёт по слепку ETL.

## Метрики
- query latency, conflict-count, graph size.

## Требования
[R-F3][R-F4][R-F5][R-N3][R-K4][R-OUT5]
