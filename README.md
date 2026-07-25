# Quantum Analytics

Quantum — локальный read-only центр финансовых решений для отчётов Wildberries.
Текущий пользовательский продукт — Windows desktop-приложение, а не облачный API-сервис.

## Что делает текущая версия

- загружает и проверяет отчёты локально;
- показывает пользователю обнаруженную XLSX-схему до импорта;
- требует отдельного подтверждения полномочий и схемы;
- сохраняет проверенную immutable-копию исходного отчёта внутри Quantum;
- восстанавливает отчёты после перезапуска без повторного выбора файла;
- рассчитывает экономику по подтверждённым товарным группам;
- требует явного ввода налоговой ставки, налоговой базы, себестоимости и прочих расходов;
- учитывает расходы Wildberries без артикула отдельно, не создавая фиктивную товарную атрибуцию;
- формирует локальные JSON, Excel и HTML-результаты;
- не выполняет запись на Wildberries или другой маркетплейс.

## Основной запуск

Windows release package создаёт ярлык **«Центр решений Quantum»**.
Для запуска из исходников:

```powershell
python -m quantum.application.desktop_center \
  --root . \
  --config config/default-home-local.json
```

Проверка установленного runtime:

```powershell
python -m quantum.application.desktop_center \
  --root . \
  --config config/default-home-local.json \
  --self-test
```

Self-test возвращает ненулевой код, если не прошёл хотя бы один вложенный контроль.

## Сборка Python-пакета

Проект использует стандартный backend `setuptools.build_meta`.

```bash
python -m pip wheel --no-deps .
```

Публичные entry points:

- `quantum-desktop`;
- `quantum-local-pilot`;
- `quantum-ci`.

## Финансовая модель

Quantum не подставляет отсутствующие коммерческие значения.
Профиль считается подтверждённым только после явного выбора:

- налоговой ставки;
- налоговой базы;
- прочих расходов на проданную единицу;
- себестоимости каждой товарной группы.

Поддерживаемые налоговые базы текущего профиля:

- продажи/возвраты до удержаний Wildberries;
- доход после расходов Wildberries.

Выбор зависит от применяемого налогового режима и подтверждается пользователем; Quantum не выбирает его самостоятельно.

## Безопасность и конфиденциальность

- исходные коммерческие данные не отправляются в GitHub или внешние модели;
- durable report index не сохраняет абсолютные внешние пути пользователя;
- исходник проверяется по SHA-256;
- расчёт разбирает те же байты XLSX, которые были хешированы;
- Microsoft Defender не отключается;
- marketplace writes отключены.

## Проверки

Release candidate проверяется на одном exact head через Linux и Windows контуры:
Foundation, OSS admission, baseline/reproduction, security/performance, clean environment,
ACL recovery, launcher tests, universal file corpus, installer build, package inventory,
production repair и Native Red Team.

Исторический PASS не переносится автоматически на новый commit.

## Статус релиза

`RELEASE_BLOCKED`

Автоматический технический PASS не заменяет:

- Authenticode-подпись установщика;
- физическую проверку на компьютере пользователя;
- подтверждение реального налогового режима и налоговой базы;
- отдельное решение о merge в `main`.

Текущее состояние и открытые ограничения фиксируются в
`docs/governance/CURRENT_STATE.md` и milestone/red-team evidence files.
