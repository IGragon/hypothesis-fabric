# Spec: Serving & Config (M11) — Вариант 2

> API, конфигурация, секреты, версии моделей. Ссылается на
> `02-container.md` (Containers 2, 10).

## Роль
REST-шлюз (API Gateway), конфигурация системы, секреты, управление версиями
LLM. Обеспечение on-prem развёртывания [R-N5].

## Запуск
- Контейнеры on-prem (Docker/K8s): Web App, API Gateway, Orchestrator, ETL,
  Retriever, KG, Generator, Scorer, Storage, LLM Runtime, Observability [R-N5].
- LLM Runtime — изолированный on-prem инференс [AD-9][ASSUM-3].
- ETL — batch-расписание (Airflow/Prefect) [R-F1].

## Конфигурация
- Параметры: context budget (16k/slot), per-stage timeout, веса ранжирования
  [R-A1], deny-list, toggle внешних API [R-N5].
- Режимы: «строгая конфиденциальность» (внешние off) vs «расширенный поиск».

## Секреты
- On-prem secret-менеджер; RBAC; ключи шифрования Storage [R-N5].

## Версии моделей
- Версионирование LLM и schema слотов; A/B-переключатель.
- Регрессионные evals (M12) при смене модели [R-N1].

## Требования
[R-N4][R-N5][R-A1][R-F1][ASSUM-3]
