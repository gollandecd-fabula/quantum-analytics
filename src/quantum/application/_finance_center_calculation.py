from __future__ import annotations

from quantum.application._finance_center_shared import *


class FinanceCenterCalculationMixin:
        def _detailed_report(self) -> ImportRow | None:
            candidates: list[ImportRow] = []
            for state in self.reports.values():
                row = state.row
                if row.status in {"Ошибка", "Недоступен", "Отменено"}:
                    continue
                if not row.source_path.is_file():
                    continue
                bridge = row.report.get("source_bridge") if isinstance(row.report, dict) else None
                source_type = bridge.get("source_type") if isinstance(bridge, dict) else None
                if row.detected_format == "WB_DETAILED_FINANCIAL" or source_type == "WB_DETAILED_FINANCIAL":
                    candidates.append(row)
                    continue
                if isinstance(row.report, dict) and row.report.get("source_type") == "WB_DETAILED_FINANCIAL":
                    candidates.append(row)
            return candidates[-1] if candidates else None

        def calculate_finance(self) -> None:
            missing = validate_profile(self.profile)
            if missing:
                messagebox.showerror(APP_TITLE, "Расчёт заблокирован:\n\n" + "\n".join(f"• {item}" for item in missing))
                self.open_finance_profile()
                return
            detailed = self._detailed_report()
            if detailed is None:
                messagebox.showwarning(
                    APP_TITLE,
                    "Для расчёта нужен детализированный финансовый отчёт Wildberries. "
                    "Если он был загружен ранее, проверьте раздел «Контроль данных»: "
                    "Quantum должен восстановить сохранённый исходник автоматически.",
                )
                return
            config = _safe_json(self.config_path)
            organization_id = str(config.get("tenant_id") or "").strip()
            if not organization_id:
                messagebox.showerror(APP_TITLE, "В локальной конфигурации отсутствует tenant_id.")
                return
            self.set_status("Финансовый расчёт выполняется по подтверждённым группам.", "info")
            try:
                source_payload = detailed.source_path.read_bytes()
                source_hash = sha256(source_payload).hexdigest()
                expected_hash = (
                    str(detailed.report.get("file_sha256") or "").strip().lower()
                    if isinstance(detailed.report, dict)
                    else ""
                )
                if expected_hash and source_hash != expected_hash:
                    raise FinanceProfileError(
                        "SOURCE_FILE_HASH_MISMATCH",
                        (str(detailed.source_path),),
                    )
                rows = read_detailed_financial_rows(detailed.source_path, detailed.report)
                result = calculate_by_group(
                    detailed_rows=rows,
                    profile=self.profile,
                    organization_id=organization_id,
                    source_id="home-local:" + (
                        str(
                            detailed.details.get("original_source_name")
                            or detailed.source_path.name
                        )
                    ),
                    source_sha256=source_hash,
                )
                output_dir = self.project_root / "output"
                output_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                json_path = output_dir / f"Quantum_Finance_{stamp}.json"
                xlsx_path = output_dir / f"Quantum_Report_{stamp}.xlsx"
                dashboard_path = output_dir / f"Quantum_Dashboard_{stamp}.html"
                save_run_result(json_path, result)
                write_run_result_xlsx(xlsx_path, result)
                write_run_dashboard(dashboard_path, result)
            except FinanceProfileError as exc:
                messagebox.showerror(APP_TITLE, self.describe_error(exc))
                self.set_status("Финансовый расчёт заблокирован.", "error")
                return
            except OSError as exc:
                messagebox.showerror(
                    APP_TITLE,
                    "Не удалось прочитать сохранённый отчёт или записать результат.\n\n"
                    f"Технические сведения: {type(exc).__name__}",
                )
                self.set_status("Ошибка доступа к файлам финансового расчёта.", "error")
                return
            self.current_result = result
            self.current_outputs = {"JSON": json_path, "Excel": xlsx_path, "Dashboard": dashboard_path}
            self._render_result(result)
            self.refresh_exports()
            if result.status == "CALCULATED":
                self.set_status("Финансовый расчёт завершён.", "success")
                self.show_page("analytics")
            else:
                self.set_status("Расчёт заблокирован: требуются дополнительные данные.", "warning")
                messagebox.showwarning(APP_TITLE, "Расчёт не завершён:\n\n" + "\n".join(f"• {item}" for item in result.missing_inputs))
                self.open_finance_profile()

        def _render_result(self, result: FinanceRunResult) -> None:
            if result.status == "CALCULATED":
                lines = ["ПОДТВЕРЖДЁННЫЙ ФИНАНСОВЫЙ РЕЗУЛЬТАТ", ""]
                labels = {
                    "net_sold_units": "Продано единиц",
                    "net_marketplace_income_amount": "Чистый доход маркетплейса, ₽",
                    "product_cost_amount": "Себестоимость, ₽",
                    "other_expense_amount": "Прочие расходы, ₽",
                    "tax_amount": "Налог, ₽",
                    "net_profit_amount": "Чистая прибыль, ₽",
                    "profit_per_sold_unit": "Прибыль на единицу, ₽",
                }
                for metric_id, label in labels.items():
                    lines.append(f"{label}: {result.totals.get(metric_id, '—')}")
                lines.append("")
                lines.append("ПО ГРУППАМ")
                for item in result.group_results:
                    calculation = item.calculation or {}
                    metrics = calculation.get("results") if isinstance(calculation, dict) else None
                    profit = metrics.get("net_profit_amount", {}).get("value") if isinstance(metrics, dict) else None
                    lines.append(f"• {item.group_name}: прибыль {profit or '—'} ₽")
                self._set_text(self.analytics_text, "\n".join(lines))
                recommendations = self._recommendations(result)
                self._set_text(self.recommendations_text, recommendations)
                self._set_text(self.decision_text, "Расчёт выполнен без подстановки отсутствующих значений.\n\n" + recommendations)
            else:
                blocked = "РАСЧЁТ ЗАБЛОКИРОВАН\n\n" + "\n".join(f"• {item}" for item in result.missing_inputs)
                self._set_text(self.analytics_text, blocked)
                self._set_text(self.recommendations_text, "Управленческие рекомендации по прибыли не сформированы.\n\n" + blocked)
                self._set_text(self.decision_text, blocked)
            self.refresh_cards()
            self.refresh_quality()

        def _recommendations(self, result: FinanceRunResult) -> str:
            group_profit: list[tuple[str, float]] = []
            for item in result.group_results:
                if item.state != "VALID" or not item.calculation:
                    continue
                raw = item.calculation["results"]["net_profit_amount"]["value"]
                try:
                    group_profit.append((item.group_name, float(raw)))
                except (TypeError, ValueError):
                    continue
            lines = ["ПРИОРИТЕТЫ ПО ПРИБЫЛИ", ""]
            for group_name, profit in sorted(group_profit, key=lambda value: value[1]):
                if profit < 0:
                    lines.append(f"КРИТИЧЕСКИЙ ПРИОРИТЕТ: {group_name} — убыток {profit:.2f} ₽. Требуется проверка цены, логистики, возвратов и рекламы.")
                else:
                    lines.append(f"{group_name}: прибыль {profit:.2f} ₽. Рекомендация требует оценки устойчивости продаж и рекламной эффективности.")
            if not group_profit:
                lines.append("Нет подтверждённых групповых результатов.")
            lines.append("")
            lines.append("Любое действие является рекомендацией и не выполняется на Wildberries автоматически.")
            return "\n".join(lines)

        def refresh_cards(self) -> None:
            if not hasattr(self, "decision_cards"):
                return
            self.decision_cards["reports"].configure(text=str(len(self.reports)))
            self.decision_cards["groups"].configure(text=str(len(self.profile.groups)))
            self.decision_cards["profile"].configure(text="ГОТОВ" if not validate_profile(self.profile) else "НЕПОЛНЫЙ")
            self.decision_cards["calculation"].configure(text="ГОТОВ" if self.current_result and self.current_result.status == "CALCULATED" else "НЕТ")

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
                + str(sum(state.row.source_path.is_file() for state in self.reports.values()))
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
                lines.extend(f"• {item}" for item in self.current_result.missing_inputs)
            lines.extend(("", "Marketplace: WILDBERRIES", "Режим: WB_ONLY", "Запись на маркетплейс: отключена"))
            if hasattr(self, "quality_text"):
                self._set_text(self.quality_text, "\n".join(lines))


__all__ = [name for name in globals() if not name.startswith("__")]
