from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any
from uuid import uuid4

from quantum.application._finance_center_shared import *
from quantum.application._finance_profile_financial_rows import (
    PERIOD_TAX_GROUP,
    UNALLOCATED_SERVICE_GROUP,
)
from quantum.application._finance_generic_tabular import (
    extract_metric_groups,
    merge_metric_groups,
)
from quantum.pilot.universal_tables import extract_tables
from quantum.insights.financial import (
    FinancialRecommendationError,
    build_financial_recommendations,
)


_RECOMMENDATIONS_SCHEMA_VERSION = "quantum-finance-recommendations-v1"
_MAX_FINANCE_SOURCE_BYTES = 100 * 1024 * 1024
_ACTION_LABELS = {
    "RESTORE_BREAK_EVEN": "Восстановить безубыточность",
    "RESOLVE_RECONCILIATION_CONFLICT": (
        "Устранить расхождение контрольных итогов"
    ),
}


def _recommendation_action_label(item: Mapping[str, Any]) -> str:
    code = str(item.get("action_code") or "").strip()
    if not code:
        return "Действие не определено"
    return _ACTION_LABELS.get(code, "Проверить рекомендацию: " + code)



def _read_finance_source(path: Path) -> bytes:
    if not path.is_file():
        raise FinanceProfileError("SOURCE_FILE_NOT_FOUND")
    try:
        with path.open("rb") as stream:
            payload = stream.read(_MAX_FINANCE_SOURCE_BYTES + 1)
    except OSError as exc:
        raise FinanceProfileError("SOURCE_FILE_READ_FAILED") from exc
    if len(payload) > _MAX_FINANCE_SOURCE_BYTES:
        raise FinanceProfileError(
            "SOURCE_FILE_TOO_LARGE",
            (str(_MAX_FINANCE_SOURCE_BYTES),),
        )
    if not payload:
        raise FinanceProfileError("SOURCE_FILE_EMPTY")
    return payload

def _new_finance_run_id() -> str:
    return (
        datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        + "_"
        + uuid4().hex[:12]
    )


def _fsync_file(path: Path) -> None:
    # Windows FlushFileBuffers requires a handle opened with write access.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cleanup_stale_staging(
    output_dir: Path,
    *,
    minimum_age_seconds: float = 3600.0,
) -> tuple[Path, ...]:
    cutoff = time.time() - max(0.0, minimum_age_seconds)
    removed: list[Path] = []
    if not output_dir.is_dir():
        return ()
    for path in sorted(output_dir.glob(".quantum-run-*.tmp")):
        try:
            if path.is_symlink() or not path.is_dir():
                continue
            if path.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(path)
        removed.append(path)
    return tuple(removed)


def _recommendation_source_refs(
    calculation: Mapping[str, Any],
) -> tuple[str, ...]:
    refs: set[str] = set()
    results = calculation.get("results")
    if not isinstance(results, Mapping):
        return ()
    for metric in results.values():
        if not isinstance(metric, Mapping):
            continue
        source_ids = metric.get("source_ids")
        if not isinstance(source_ids, Sequence) or isinstance(
            source_ids,
            (str, bytes),
        ):
            continue
        refs.update(
            item
            for item in source_ids
            if isinstance(item, str) and item.strip()
        )
    return tuple(sorted(refs))


def _build_governed_recommendations(
    result: FinanceRunResult,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for group in result.group_results:
        if (
            group.state != "VALID"
            or not group.calculation
            or "ZERO_ACTIVITY" in group.reason_codes
            or group.group_name in {PERIOD_TAX_GROUP, UNALLOCATED_SERVICE_GROUP}
        ):
            continue
        try:
            recommendations = build_financial_recommendations(
                calculation=group.calculation,
                reconciliation={"state": "NOT_REQUESTED"},
                source_type="WB_DETAILED_FINANCIAL",
                source_refs=_recommendation_source_refs(group.calculation),
                scope={"product_group": group.group_name},
            )
        except FinancialRecommendationError as exc:
            errors.append(f"{group.group_name}: {exc.code}")
            continue
        records.extend(
            {
                "group_name": group.group_name,
                "recommendation": recommendation,
            }
            for recommendation in recommendations
        )
    return tuple(records), tuple(sorted(set(errors)))


def _write_recommendation_payload(
    path: Path,
    *,
    records: Sequence[Mapping[str, Any]],
    errors: Sequence[str],
) -> None:
    payload = {
        "schema_version": _RECOMMENDATIONS_SCHEMA_VERSION,
        "recommendation_count": len(records),
        "recommendations": [dict(record) for record in records],
        "errors": list(errors),
        "marketplace_write_enabled": False,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _write_finance_output_bundle(
    output_dir: Path,
    result: FinanceRunResult,
) -> tuple[dict[str, Path], tuple[dict[str, Any], ...], tuple[str, ...]]:
    """Publish one complete run directory or nothing.

    A run is first materialized under a private staging directory.  Every
    artifact is checked and flushed before one atomic directory rename makes
    the run visible.  This prevents mixed/partial JSON-XLSX-dashboard states
    after disk errors or process interruption.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_staging(output_dir)
    run_id = _new_finance_run_id()
    final_dir = output_dir / f"Quantum_Run_{run_id}"
    stage_dir = Path(
        tempfile.mkdtemp(
            dir=output_dir,
            prefix=f".quantum-run-{run_id}-",
            suffix=".tmp",
        )
    )
    recommendations, recommendation_errors = (
        _build_governed_recommendations(result)
    )
    try:
        staged = {
            "JSON": stage_dir / f"Quantum_Finance_{run_id}.json",
            "Recommendations": (
                stage_dir / f"Quantum_Recommendations_{run_id}.json"
            ),
            "Excel": stage_dir / f"Quantum_Report_{run_id}.xlsx",
            "Dashboard": stage_dir / f"Quantum_Dashboard_{run_id}.html",
        }
        save_run_result(staged["JSON"], result)
        _write_recommendation_payload(
            staged["Recommendations"],
            records=recommendations,
            errors=recommendation_errors,
        )
        write_run_result_xlsx(
            staged["Excel"],
            result,
            recommendations=recommendations,
            recommendation_errors=recommendation_errors,
        )
        write_run_dashboard(
            staged["Dashboard"],
            result,
            recommendations=recommendations,
            recommendation_errors=recommendation_errors,
        )
        for path in staged.values():
            if not path.is_file() or path.stat().st_size <= 0:
                raise OSError("FINANCE_OUTPUT_BUNDLE_INCOMPLETE")
            _fsync_file(path)
        _fsync_directory(stage_dir)
        os.replace(stage_dir, final_dir)
        _fsync_directory(output_dir)
        outputs = {
            label: final_dir / path.name
            for label, path in staged.items()
        }
        return outputs, recommendations, recommendation_errors
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise


class FinanceCenterCalculationMixin:
    def _detailed_report(self) -> ImportRow | None:
        """Compatibility selector; universal calculations no longer require it."""
        candidates = [
            row
            for row in self._finance_sources()
            if (
                row.detected_format == "WB_DETAILED_FINANCIAL"
                or (
                    isinstance(row.report, Mapping)
                    and (
                        row.report.get("source_type") == "WB_DETAILED_FINANCIAL"
                        or (
                            isinstance(row.report.get("source_bridge"), Mapping)
                            and row.report["source_bridge"].get("source_type")
                            == "WB_DETAILED_FINANCIAL"
                        )
                    )
                )
            )
        ]
        return candidates[-1] if candidates else None

    def _finance_sources(self) -> tuple[ImportRow, ...]:
        candidates: list[ImportRow] = []
        for state in self.reports.values():
            row = state.row
            if row.status in {"Ошибка", "Недоступен", "Отменено"}:
                continue
            if row.source_path.is_file():
                candidates.append(row)
        return tuple(sorted(candidates, key=lambda row: row.row_id))

    def _collect_universal_evidence(
        self,
        sources: Sequence[ImportRow],
    ) -> tuple[tuple[Any, ...], tuple[dict[str, Any], ...], dict[str, Any]]:
        evidence: list[Any] = []
        unresolved: list[dict[str, Any]] = []
        seen_file_hashes: set[str] = set()
        processed = 0
        with_tables = 0
        for row in sources:
            try:
                payload = _read_finance_source(row.source_path)
            except FinanceProfileError as exc:
                unresolved.append(
                    {
                        "scope": row.source_path.name,
                        "state": "FAILED",
                        "reason_codes": [exc.code],
                        "source_name": row.source_path.name,
                    }
                )
                continue
            file_hash = sha256(payload).hexdigest()
            if file_hash in seen_file_hashes:
                unresolved.append(
                    {
                        "scope": row.source_path.name,
                        "state": "SKIPPED_DUPLICATE",
                        "reason_codes": ["DUPLICATE_FILE_SHA256"],
                        "source_name": row.source_path.name,
                    }
                )
                continue
            seen_file_hashes.add(file_hash)
            expected_hash = (
                str(row.report.get("file_sha256") or "").strip().lower()
                if isinstance(row.report, dict)
                else ""
            )
            if expected_hash and expected_hash != file_hash:
                unresolved.append(
                    {
                        "scope": row.source_path.name,
                        "state": "FAILED",
                        "reason_codes": ["SOURCE_FILE_HASH_MISMATCH"],
                        "source_name": row.source_path.name,
                    }
                )
                continue
            processed += 1
            try:
                extraction = extract_tables(
                    payload,
                    source_name=row.source_path.name,
                )
            except Exception as exc:
                unresolved.append(
                    {
                        "scope": row.source_path.name,
                        "state": "FAILED",
                        "reason_codes": [
                            getattr(
                                exc,
                                "code",
                                "UNIVERSAL_EXTRACTION_UNEXPECTED_ERROR",
                            )
                        ],
                        "source_name": row.source_path.name,
                    }
                )
                continue
            if extraction.tables:
                with_tables += 1
                evidence.extend(
                    extract_metric_groups(
                        extraction.tables,
                        product_to_group=self.profile.product_to_group,
                    )
                )
            if extraction.status != "COMPLETE" or not extraction.tables:
                unresolved.append(
                    {
                        "scope": row.source_path.name,
                        "state": extraction.status,
                        "reason_codes": list(
                            extraction.reason_codes
                            or (("NO_USABLE_FINANCIAL_FIELDS",) if not extraction.tables else ())
                        ),
                        "source_name": row.source_path.name,
                        "member_results": [item.to_dict() for item in extraction.members],
                    }
                )
        coverage = {
            "uploaded_file_count": len(sources),
            "processed_file_count": processed,
            "files_with_tables": with_tables,
            "files_without_tables_or_partial": len(unresolved),
        }
        return merge_metric_groups(tuple(evidence)), tuple(unresolved), coverage

    def calculate_finance(self) -> None:
        sources = self._finance_sources()
        if not sources:
            messagebox.showwarning(
                APP_TITLE,
                "Загрузите любые имеющиеся файлы отчётов или архивы. "
                "Quantum обработает доступные таблицы и отдельно укажет, "
                "какие показатели нельзя рассчитать.",
            )
            return
        config = _safe_json(self.config_path)
        organization_id = str(config.get("tenant_id") or "home-local").strip()
        self.set_status(
            "Quantum извлекает доступные данные из всех загруженных файлов.",
            "info",
        )
        try:
            evidence, file_unresolved, file_coverage = (
                self._collect_universal_evidence(sources)
            )
            if evidence:
                base_result = calculate_metric_groups(
                    evidence_groups=evidence,
                    profile=self.profile,
                    organization_id=organization_id,
                )
                missing = list(base_result.missing_inputs)
                missing.extend(
                    f"{scope.get('scope', 'Файл')}: {reason}"
                    for scope in file_unresolved
                    for reason in scope.get("reason_codes", [])
                    if reason
                )
                result = FinanceRunResult(
                    status=(
                        "CALCULATED_PARTIAL"
                        if file_unresolved and base_result.status == "CALCULATED"
                        else base_result.status
                    ),
                    group_results=base_result.group_results,
                    totals=base_result.totals,
                    missing_inputs=tuple(sorted(set(missing))),
                    metric_states=base_result.metric_states,
                    coverage={**base_result.coverage, **file_coverage},
                    unresolved_scopes=tuple(
                        (*base_result.unresolved_scopes, *file_unresolved)
                    ),
                )
            else:
                reasons = tuple(
                    sorted(
                        set(
                            f"{scope.get('scope', 'Файл')}: {reason}"
                            for scope in file_unresolved
                            for reason in scope.get("reason_codes", [])
                            if reason
                        )
                        or {"NO_USABLE_FINANCIAL_FIELDS"}
                    )
                )
                result = FinanceRunResult(
                    status="CALCULATION_BLOCKED",
                    group_results=(),
                    totals={},
                    missing_inputs=reasons,
                    metric_states={},
                    coverage=file_coverage,
                    unresolved_scopes=file_unresolved,
                )
            (
                outputs,
                recommendations,
                recommendation_errors,
            ) = _write_finance_output_bundle(
                self.project_root / "output",
                result,
            )
        except FinanceProfileError as exc:
            messagebox.showerror(APP_TITLE, self.describe_error(exc))
            self.set_status("Ошибка финансового анализа.", "error")
            return
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE,
                "Не удалось прочитать сохранённые файлы или записать "
                "результат.\n\n"
                f"Технические сведения: {type(exc).__name__}",
            )
            self.set_status("Ошибка доступа к файлам анализа.", "error")
            return
        self.current_result = result
        self.current_outputs = outputs
        self.current_recommendations = recommendations
        self.current_recommendation_errors = recommendation_errors
        self._render_result(result)
        self.refresh_exports()
        self.show_page("analytics")
        if result.status == "CALCULATED":
            self.set_status("Все доступные показатели рассчитаны.", "success")
        elif result.status == "CALCULATED_PARTIAL":
            self.set_status(
                "Доступные показатели рассчитаны; часть требует данных.",
                "warning",
            )
            messagebox.showwarning(
                APP_TITLE,
                "Quantum сохранил все рассчитанные показатели.\n\n"
                "Для остальных нужны данные:\n"
                + "\n".join(f"• {item}" for item in result.missing_inputs[:30]),
            )
        else:
            self.set_status(
                "Финансовых полей для расчёта недостаточно; файлы сохранены.",
                "warning",
            )
            messagebox.showwarning(
                APP_TITLE,
                "Загруженные файлы обработаны, но финансовый расчёт пока "
                "невозможен.\n\nНужны данные:\n"
                + "\n".join(f"• {item}" for item in result.missing_inputs[:30]),
            )

    def _render_result(self, result: FinanceRunResult) -> None:
        labels = {
            "net_sold_units": "Продано единиц",
            "gross_sales_amount": "Продажи/возвраты, ₽",
            "net_marketplace_income_amount": "Доход после расходов WB, ₽",
            "product_cost_amount": "Себестоимость, ₽",
            "other_expense_amount": "Прочие расходы, ₽",
            "pre_tax_profit_amount": "Прибыль до налога, ₽",
            "tax_amount": "Налог, ₽",
            "net_profit_amount": "Чистая прибыль, ₽",
            "profit_per_sold_unit": "Прибыль на единицу, ₽",
        }
        calculated = ["РАССЧИТАНО", ""]
        unavailable = ["НЕ РАССЧИТАНО", ""]
        for metric_id, label in labels.items():
            state = result.metric_states.get(metric_id, {})
            value = result.totals.get(metric_id)
            metric_state = str(state.get("state") or ("VALID" if value is not None else "BLOCKED"))
            if value is not None:
                suffix = " (частичный охват)" if metric_state == "PARTIAL" else ""
                calculated.append(f"{label}: {value}{suffix}")
            else:
                reasons = "; ".join(str(item) for item in state.get("reason_codes", []))
                unavailable.append(f"{label}: {reasons or 'недостаточно данных'}")
        if len(calculated) == 2:
            calculated.append("Финансовые показатели пока не извлечены.")
        if len(unavailable) == 2:
            unavailable.append("Нет заблокированных показателей.")
        coverage = ["", "ОХВАТ"]
        for key, value in sorted(result.coverage.items()):
            coverage.append(f"• {key}: {value}")
        groups = ["", "ПО ИСТОЧНИКАМ И ГРУППАМ"]
        for item in result.group_results:
            groups.append(
                f"• {item.group_name}: {item.state}"
                + (
                    " — " + "; ".join(item.reason_codes)
                    if item.reason_codes and item.state != "VALID"
                    else ""
                )
            )
        needs = ["", "НУЖНЫ ДАННЫЕ"]
        needs.extend(f"• {item}" for item in result.missing_inputs)
        if len(needs) == 2:
            needs.append("Дополнительные данные не требуются.")
        text = "\n".join((*calculated, *unavailable, *coverage, *groups, *needs))
        self._set_text(self.analytics_text, text)
        recommendations = self._recommendations(result)
        self._set_text(self.recommendations_text, recommendations)
        self._set_text(
            self.decision_text,
            "Quantum не подставляет отсутствующие значения. Все доступные "
            "цифры сохранены; недоступные показатели перечислены отдельно.\n\n"
            + recommendations,
        )
        self.refresh_cards()
        self.refresh_quality()

    def _recommendations(self, result: FinanceRunResult) -> str:
        governed = getattr(self, "current_recommendations", ())
        governed_errors = getattr(
            self,
            "current_recommendation_errors",
            (),
        )
        if governed:
            lines = ["РЕКОМЕНДАЦИИ С ДОКАЗАТЕЛЬСТВАМИ", ""]
            for record in governed:
                item = record.get("recommendation", {})
                forecast = item.get("forecast_effect", {})
                confidence = item.get("confidence", {})
                lines.extend(
                    (
                        f"• {record.get('group_name', 'Общие данные')}: "
                        f"{_recommendation_action_label(item)}",
                        "  Текущий эффект: "
                        f"{item.get('current_effect', {}).get('amount', '—')} ₽",
                        "  Прогноз: "
                        f"{forecast.get('amount_min', '—')}…"
                        f"{forecast.get('amount_max', '—')} ₽",
                        "  Уверенность: "
                        f"{confidence.get('state', 'UNVERIFIED')}",
                        "  Ограничения: "
                        + (
                            "; ".join(item.get("limitations", []))
                            or "нет"
                        ),
                        "",
                    )
                )
            lines.append(
                "Любое действие является рекомендацией и не выполняется "
                "на Wildberries автоматически."
            )
            return "\n".join(lines)

        group_profit: list[tuple[str, Decimal]] = []
        period_tax: Decimal | None = None
        service_impact: Decimal | None = None
        zero_activity: list[str] = []
        for item in result.group_results:
            if item.state != "VALID":
                continue
            if "ZERO_ACTIVITY" in item.reason_codes:
                zero_activity.append(item.group_name)
                continue
            if not item.calculation:
                continue
            raw = item.calculation["results"]["net_profit_amount"][
                "value"
            ]
            try:
                value = Decimal(str(raw))
                if not value.is_finite():
                    raise InvalidOperation
            except (InvalidOperation, TypeError, ValueError):
                continue
            if item.group_name == PERIOD_TAX_GROUP:
                period_tax = -value
            elif item.group_name == UNALLOCATED_SERVICE_GROUP:
                service_impact = value
            else:
                group_profit.append((item.group_name, value))
        lines = ["ПРИОРИТЕТЫ ПО ПРИБЫЛИ", ""]
        for group_name, profit in sorted(
            group_profit,
            key=lambda value: value[1],
        ):
            if profit < 0:
                lines.append(
                    f"КРИТИЧЕСКИЙ ПРИОРИТЕТ: {group_name} — "
                    f"убыток до налога {profit:.2f} ₽. Требуется проверка "
                    "цены, логистики, возвратов и рекламы."
                )
            else:
                lines.append(
                    f"{group_name}: прибыль до налога {profit:.2f} ₽. "
                    "Налог показан отдельно на уровне периода."
                )
        if service_impact is not None:
            lines.append(
                "Расходы WB без артикула изменили прибыль на "
                f"{service_impact:.2f} ₽; они не потеряны и не отнесены "
                "к товару без доказуемого ключа."
            )
        if period_tax is not None:
            lines.append(f"Налог периода: {period_tax:.2f} ₽.")
        if zero_activity:
            lines.append(
                "Нет операций в периоде: "
                + ", ".join(sorted(zero_activity))
                + "."
            )
        if not group_profit:
            lines.append(
                "Нет подтверждённых активных товарных групп или "
                "нет доказуемого основания для управленческой рекомендации."
            )
        if governed_errors:
            lines.append(
                "Ошибки построения рекомендаций: "
                + "; ".join(governed_errors)
            )
        lines.append("")
        lines.append(
            "Любое действие является рекомендацией и не выполняется "
            "на Wildberries автоматически."
        )
        return "\n".join(lines)

    def refresh_cards(self) -> None:
        if not hasattr(self, "decision_cards"):
            return
        self.refresh_decision_center()

    def refresh_exports(self) -> None:
        self.export_list.delete(0, tk.END)
        for label, path in self.current_outputs.items():
            self.export_list.insert(tk.END, f"{label}: {path}")

    def open_export(self) -> None:
        selection = self.export_list.curselection()
        if not selection:
            return
        text = self.export_list.get(selection[0])
        _label, raw_path = text.split(": ", 1)
        path = Path(raw_path)
        if path.exists():
            _open_path(path)

    def refresh_quality(self) -> None:
        lines = ["КОНТРОЛЬ ДАННЫХ", ""]
        lines.append(f"Отчётов загружено: {len(self.reports)}")
        lines.append(
            "Сохранённых исходников доступно: "
            + str(
                sum(
                    state.row.source_path.is_file()
                    for state in self.reports.values()
                )
            )
        )
        lines.append(f"Товаров определено: {len(self.products)}")
        lines.append(f"Товарных групп: {len(self.profile.groups)}")
        missing = validate_profile(self.profile)
        if missing:
            lines.append("")
            lines.append("ОБЯЗАТЕЛЬНЫЕ ДАННЫЕ ОТСУТСТВУЮТ")
            lines.extend(f"• {item}" for item in missing)
        else:
            lines.append("Обязательные поля профиля заполнены.")
        if self.current_result and self.current_result.missing_inputs:
            lines.append("")
            lines.append("БЛОКЕРЫ ПО ФАКТИЧЕСКОМУ ОТЧЁТУ")
            lines.extend(
                f"• {item}"
                for item in self.current_result.missing_inputs
            )
        lines.extend(
            (
                "",
                "Marketplace: WILDBERRIES",
                "Режим: WB_ONLY",
                "Запись на маркетплейс: отключена",
            )
        )
        if hasattr(self, "quality_text"):
            self._set_text(self.quality_text, "\n".join(lines))


__all__ = [name for name in globals() if not name.startswith("__")]
