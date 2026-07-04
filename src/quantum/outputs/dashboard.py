from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .local_bundle import validate_local_output_bundle


_ACTION_LABELS = {
    "COMPLETE_REQUIRED_INPUTS": "Заполнить обязательные данные",
    "INVESTIGATE_LOW_BUYOUT": "Разобрать низкий выкуп",
    "REVIEW_STOCKOUT": "Проверить дефицит остатка",
    "REVIEW_STOCK_WITHOUT_BUYOUT": "Проверить остаток без выкупа",
    "REVIEW_HIGH_STOCK_TO_BUYOUT_RATIO": "Проверить избыточный остаток",
    "INVESTIGATE_HIGH_RETURN_RATE": "Разобрать высокий уровень возвратов",
    "REVIEW_COMMISSION_AND_PRICE_STRUCTURE": "Проверить комиссию и цену",
    "REVIEW_FORWARD_LOGISTICS_COST": "Проверить прямую логистику",
    "REVIEW_REVERSE_LOGISTICS_COST": "Проверить обратную логистику",
    "REVIEW_STORAGE_COST": "Проверить стоимость хранения",
    "RECONCILE_SETTLEMENT_GAP": "Сверить расхождение выплаты",
}


def _embedded_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_dashboard_html(bundle: Mapping[str, Any]) -> bytes:
    validate_local_output_bundle(bundle)
    payload = _embedded_json(bundle)
    labels = _embedded_json(_ACTION_LABELS)
    document = f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quantum Analytics</title>
<style>
:root{{--bg:#f5f7fa;--panel:#fff;--text:#17202a;--muted:#667085;--border:#dfe3e8;--critical:#b42318;--high:#b54708;--medium:#175cd3;--low:#475467}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text)}}
header{{padding:24px 28px;background:#111827;color:white}}header h1{{margin:0 0 6px;font-size:24px}}header p{{margin:0;color:#cbd5e1}}
main{{padding:24px;max-width:1500px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:18px}}
.card,.panel{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px}}.card .key{{color:var(--muted);font-size:12px;text-transform:uppercase}}.card .value{{font-size:22px;font-weight:700;margin-top:7px;word-break:break-word}}
.panel{{margin-bottom:18px;overflow:auto}}h2{{font-size:18px;margin:0 0 14px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid var(--border);padding:9px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#f8fafc}}
input,select{{border:1px solid var(--border);border-radius:6px;padding:8px;margin:0 8px 10px 0}}.badge{{display:inline-block;padding:3px 7px;border-radius:999px;font-weight:700;font-size:11px}}
.CRITICAL{{color:var(--critical);background:#fee4e2}}.HIGH{{color:var(--high);background:#ffead5}}.MEDIUM{{color:var(--medium);background:#dbeafe}}.LOW{{color:var(--low);background:#e4e7ec}}.muted{{color:var(--muted)}}
</style>
</head>
<body>
<header><h1>Quantum Analytics</h1><p>Локальный отчёт. Внешние библиотеки и сетевые запросы отсутствуют.</p></header>
<main>
<section id="summary" class="grid"></section>
<section class="panel"><h2>Показатели</h2><table><thead><tr><th>Метрика</th><th>Состояние</th><th>Значение</th><th>Единица</th><th>Валюта</th></tr></thead><tbody id="metrics"></tbody></table></section>
<section class="panel"><h2>Рекомендации</h2><input id="search" placeholder="Поиск"><select id="severity"><option value="">Все приоритеты</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select><select id="category"><option value="">Все категории</option></select><table><thead><tr><th>Приоритет</th><th>Категория</th><th>Действие</th><th>Текущий эффект</th><th>Прогноз</th><th>Уверенность</th><th>Ограничения</th></tr></thead><tbody id="recommendations"></tbody></table></section>
<section class="panel"><h2>Ограничения</h2><ul id="limitations"></ul></section>
<section class="panel"><h2>Контроль</h2><div class="muted" id="control"></div></section>
</main>
<script id="bundle-data" type="application/json">{payload}</script>
<script>
const B=JSON.parse(document.getElementById('bundle-data').textContent);
const LABELS={labels};
const A=B.analysis||{{}};
const R=B.recommendations||{{}};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const cards=[['Статус',B.run_status],['Источник',B.source_type||'—'],['Рекомендации',R.recommendation_count??0],['Статус рекомендаций',R.status||'—'],['Пакет',B.bundle_hash.slice(0,16)+'…']];
document.getElementById('summary').innerHTML=cards.map(x=>`<div class="card"><div class="key">${{esc(x[0])}}</div><div class="value">${{esc(x[1])}}</div></div>`).join('');
const metrics=A.observed_metrics||{{}};
document.getElementById('metrics').innerHTML=Object.keys(metrics).sort().map(k=>{{const m=metrics[k]||{{}};return `<tr><td>${{esc(k)}}</td><td>${{esc(m.state)}}</td><td>${{esc(m.value)}}</td><td>${{esc(m.unit)}}</td><td>${{esc(m.currency)}}</td></tr>`}}).join('');
const items=Array.isArray(R.recommendations)?R.recommendations:[];
const categories=[...new Set(items.map(x=>x.category).filter(Boolean))].sort();
document.getElementById('category').innerHTML+=categories.map(x=>`<option>${{esc(x)}}</option>`).join('');
function effect(e){{if(!e)return '—';if(e.amount!=null)return `${{e.amount}} ${{e.currency||''}}`;if(e.amount_min!=null||e.amount_max!=null)return `${{e.amount_min??'—'}}…${{e.amount_max??'—'}} ${{e.currency||''}}`;return e.reason_code||e.state||'—'}}
function render(){{const query=document.getElementById('search').value.toLowerCase();const severity=document.getElementById('severity').value;const category=document.getElementById('category').value;const rows=items.filter(x=>(!severity||x.severity===severity)&&(!category||x.category===category)&&(!query||JSON.stringify(x).toLowerCase().includes(query)));document.getElementById('recommendations').innerHTML=rows.map(x=>`<tr><td><span class="badge ${{esc(x.severity)}}">${{esc(x.severity)}}</span></td><td>${{esc(x.category)}}</td><td>${{esc(LABELS[x.action_code]||x.action_code)}}</td><td>${{esc(effect(x.current_effect))}}</td><td>${{esc(effect(x.forecast_effect))}}</td><td>${{esc(x.confidence?.state)}}</td><td>${{esc((x.limitations||[]).join(' | '))}}</td></tr>`).join('')}}
['search','severity','category'].forEach(id=>document.getElementById(id).addEventListener(id==='search'?'input':'change',render));
render();
document.getElementById('limitations').innerHTML=(B.limitations||[]).map(x=>`<li>${{esc(x)}}</li>`).join('');
document.getElementById('control').textContent=`Bundle SHA-256: ${{B.bundle_hash}} · Source SHA-256: ${{B.source_sha256}} · Generated: ${{B.generated_at}}`;
</script>
</body>
</html>'''
    return document.encode("utf-8")
