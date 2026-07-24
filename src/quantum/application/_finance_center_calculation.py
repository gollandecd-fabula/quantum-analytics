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
    read_detailed_financial_rows_payload,
)
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
        raise FinanceProfileError("XLSX_FILE_NOT_FOUND")
    try:
        with path.open("rb") as stream:
            payload = stream.read(_MAX_FINANCE_SOURCE_BYTES + 1)
    except OSError as exc:
        raise FinanceProfileError("XLSX_FILE_READ_FAILED") from exc
    if len(payload) > _MAX_FINANCE_SOURCE_BYTES:
        raise FinanceProfileError(
            "XLSX_FILE_TOO_LARGE",
            (str(_MAX_FINANCE_SOURCE_BYTES),),
        )
    if not payload:
        raise FinanceProfileError("XLSX_BYTES_REQUIRED")
    return payload

def _new_finance_run_id() -> str:
    return (
        datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        + "_"
        + uuid4().hex[:12]
    )


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
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
        candidates: list[ImportRow] = []
        for state in self.reports.values():
            row = state.row
            if row.status in {"Ошибка", "Недоступен", "Отменено"}:
                continue
            if not row.source_path.is_file():
                continue
            bridge = (
                row.report.get("source_bridge")
                if isinstance(row.report, dict)
                else None
            )
            source_type = (
                bridge.get("source_type")
                if isinstance(bridge, dict)
                else None
            )
            if (
                row.detected_format == "WB_DETAILED_FINANCIAL"
                or source_type == "WB_DETAILED_FINANCIAL"
            ):
                candidates.append(row)
                continue
            if (
                isinstance(row.report, dict)
                and row.report.get("source_type")
                == "WB_DETAILED_FINANCIAL"
            ):
                candidates.append(row)
        return candidates[-1] if candidates else None

    def calculate_finance(self) -> None:
        missing = validate_profile(self.profile)
        if missing:
            messagebox.showerror(
                APP_TITLE,
                "Расчёт заблокирован:\n\n"
                + "\n".join(f"• {item}" for item in missing),
            )
            self.open_finance_profile()
            return
        detailed = self._detailed_report()
        if detailed is None:
            messagebox.showwarning(
                APP_TITLE,
                "Для расчёта нужен детализированный финансовый отчёт "
                "Wildberries. Если он был загружен ранее, проверьте раздел "
                "«Контроль данных»: Quantum должен восстановить сохранённый "
                "исходник автоматически.",
            )
            return
        config = _safe_json(self.config_path)
        organization_id = str(config.get("tenant_id") or "").strip()
        if not organization_id:
            messagebox.showerror(
                APP_TITLE,
                "В локальной конфигурации отсутствует tenant_id.",
            )
            return
        self.set_status(
            "Финансовый расчёт выполняется по подтверждённым группам.",
            "info",
        )
        try:
            source_payload = _read_finance_source(detailed.source_path)
            source_hash = sha256(source_payload).hexdigest()
            expected_hash = (
                str(detailed.report.get("file_sha256") or "")
                .strip()
                .lower()
                if isinstance(detailed.report, dict)
                else ""
            )
            if expected_hash and source_hash != expected_hash:
                raise FinanceProfileError(
                    "SOURCE_FILE_HASH_MISMATCH",
                    (str(detailed.source_path),),
                )
            # Parse the exact immutable byte string whose digest was accepted.
            # Reopening the path here would create a hash/parse TOCTOU window.
            rows = read_detailed_financial_rows_payload(
                source_payload,
                detailed.report,
            )
            result = calculate_by_group(
                detailed_rows=rows,
                profile=self.profile,
                organization_id=organization_id,
                source_id=(
                    "home-local:"
                    + str(
                        detailed.details.get("original_source_name")
                        or detailed.source_path.name
                    )
                ),
                source_sha256=source_hash,
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
            self.set_status("Финансовый расчёт заблокирован.", "error")
            return
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE,
                "Не удалось прочитать сохранённый отчёт или записать "
                "результат.\n\n"
                f"Технические сведения: {type(exc).__name__}",
            )
            self.set_status(
                "Ошибка доступа к файлам финансового расчёта.",
                "error",
            )
            return
        self.current_result = result
        self.current_outputs = outputs
        self.current_recommendations = recommendations
        self.current_recommendation_errors = recommendation_errors
        self._render_result(result)
        self.refresh_exports()
        if result.status == "CALCULATED":
            self.set_status("Финансовый расчёт завершён.", "success")
            self.show_page("analytics")
        else:
            self.set_status(
                "Расчёт заблокирован: требуются дополнительные данные.",
                "warning",
            )
            messagebox.showwarning(
                APP_TITLE,
                "Расчёт не завершён:\n\n"
                + "\n".join(
                    f"• {item}" for item in result.missing_inputs
                ),
            )
            self.open_finance_profile()

    def _render_result(self, result: FinanceRunResult) -> None:
        if result.status == "CALCULATED":
            lines = ["ПОДТВЕРЖДЁННЫЙ ФИНАНСОВЫЙ РЕЗУЛЬТАТ", ""]
            labels = {
                "net_sold_units": "Продано единиц",
                "net_marketplace_income_amount": (
                    "Чистый доход маркетплейса, ₽"
                ),
                "product_cost_amount": "Себестоимость, ₽",
                "other_expense_amount": "Прочие расходы, ₽",
                "tax_amount": "Налог, ₽",
                "net_profit_amount": "Чистая прибыль, ₽",
                "profit_per_sold_unit": "Прибыль на единицу, ₽",
            }
            for metric_id, label in labels.items():
                lines.append(
                    f"{label}: {result.totals.get(metric_id, '—')}"
                )
            lines.append("")
            lines.append("ПО ГРУППАМ")
            for item in result.group_results:
                calculation = item.calculation or {}
                metrics = (
                    calculation.get("results")
                    if isinstance(calculation, dict)
                    else None
                )
                profit = (
                    metrics.get("net_profit_amount", {}).get("value")
                    if isinstance(metrics, dict)
                    else None
                )
                if "ZERO_ACTIVITY" in item.reason_codes:
                    lines.append(
                        f"• {item.group_name}: операций в периоде нет"
                    )
                elif item.group_name == PERIOD_TAX_GROUP:
                    tax = (
                        metrics.get("tax_amount", {}).get("value")
                        if isinstance(metrics, dict)
                        else None
                    )
                    lines.append(
                        f"• {item.group_name}: {tax or '—'} ₽"
                    )
                elif item.group_name == UNALLOCATED_SERVICE_GROUP:
                    lines.append(
                        f"• {item.group_name}: влияние на прибыль "
                        f"{profit or '—'} ₽"
                    )
                else:
                    lines.append(
                        f"• {item.group_name}: прибыль до налога "
                        f"{profit or '—'} ₽"
                    )
            self._set_text(self.analytics_text, "\n".join(lines))
            recommendations = self._recommendations(result)
            self._set_text(
                self.recommendations_text,
                recommendations,
            )
            self._set_text(
                self.decision_text,
                "Расчёт выполнен без подстановки отсутствующих значений."
                "\n\n"
                + recommendations,
            )
        else:
            blocked = (
                "РАСЧЁТ ЗАБЛОКИРОВАН\n\n"
                + "\n".join(
                    f"• {item}" for item in result.missing_inputs
                )
            )
            self._set_text(self.analytics_text, blocked)
            self._set_text(
                self.recommendations_text,
                "Управленческие рекомендации по прибыли не сформированы."
                "\n\n"
                + blocked,
            )
            self._set_text(self.decision_text, blocked)
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
