from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .local_bundle import validate_local_output_bundle


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
    document = f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quantum Analytics</title>
<style>
:root{{--bg:#f4f6f8;--panel:#fff;--text:#17202a;--muted:#667085;--border:#dfe3e8;--critical:#b42318;--high:#b54708;--medium:#175cd3;--low:#475467;--positive:#067647;--negative:#b42318;--accent:#344054}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text)}}
header{{padding:24px 28px;background:#111827;color:white}}header h1{{margin:0 0 6px;font-size:24px}}header p{{margin:0;color:#cbd5e1}}
main{{padding:24px;max-width:1600px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:18px}}
.card,.panel{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px}}.card .key{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em}}.card .value{{font-size:22px;font-weight:700;margin-top:7px;word-break:break-word}}
.panel{{margin-bottom:18px;overflow:auto}}h2{{font-size:18px;margin:0 0 14px}}h3{{font-size:15px;margin:14px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid var(--border);padding:9px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#f8fafc;z-index:1}}
input,select{{border:1px solid var(--border);border-radius:6px;padding:8px;margin:0 8px 10px 0;background:white}}
.badge{{display:inline-block;padding:3px 7px;border-radius:999px;font-weight:700;font-size:11px}}.CRITICAL{{color:var(--critical);background:#fee4e2}}.HIGH{{color:var(--high);background:#ffead5}}.MEDIUM{{color:var(--medium);background:#dbeafe}}.LOW{{color:var(--low);background:#e4e7ec}}
.muted{{color:var(--muted)}}.positive{{color:var(--positive)}}.negative{{color:var(--negative)}}.bars{{display:grid;gap:8px}}.bar-row{{display:grid;grid-template-columns:minmax(190px,1fr) 3fr minmax(100px,.6fr);gap:10px;align-items:center}}.bar-track{{height:16px;background:#eef2f6;border-radius:999px;overflow:hidden}}.bar-fill{{height:100%;background:var(--accent);min-width:1px}}.control-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}}code{{word-break:break-all;font-size:11px}}
</style>
</head>
<body>
<header><h1>Quantum Analytics</h1><p>Локальный отчёт. Внешние библиотеки и сетевые запросы отсутствуют.</p></header>
<main>
<section id="summary" class="grid"></section>
<section class="panel"><h2>Финансовая структура</h2><div id="financial-chart" class="bars"></div></section>
<section class="panel"><h2>Финансовые результаты</h2><table><thead><tr><th>Метрика</th><th>Состояние</th><th>Значение</th><th>Валюта</th><th>Представление</th><th>Граница расходов</th></tr></thead><tbody id="finance"></tbody></table></section>
<section class="panel"><h2>Показатели источника</h2><input id="metric-search" placeholder="Поиск метрики"><table><thead><tr><th>Метрика</th><th>Состояние</th><th>Значение</th><th>Единица</th><th>Валюта</th><th>Причина</th></tr></thead><tbody id="metrics"></tbody></table></section>
<section class="panel"><h2>Рекомендации</h2><input id="search" placeholder="Поиск"><select id="severity"><option value="">Все уровни</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select><select id="priority"><option value="">Все цели</option><option>PROFIT</option><option>SUSTAINABLE_GROWTH</option><option>TURNOVER</option></select><select id="category"><option value="">Все категории</option></select><table><thead><tr><th>Срочность</th><th>Цель</th><th>Категория</th><th>Действие</th><th>Причина</th><th>Текущий эффект</th><th>Прогноз min</th><th>Прогноз max</th><th>Уверенность</th><th>Доказательства</th><th>Ограничения</th></tr></thead><tbody id="recommendations"></tbody></table></section>
<section class="panel"><h2>Качество данных</h2><div id="quality" class="control-grid"></div></section>
<section class="panel"><h2>Ограничения</h2><ul id="limitations"></ul></section>
<section class="panel"><h2>Контроль и происхождение</h2><div id="control" class="control-grid"></div></section>
</main>
<script id="bundle-data" type="application/json">{payload}</script>
<script>
const B=JSON.parse(document.getElementById('bundle-data').textContent);
const A=B.analysis||{{}},C=B.calculation||{{}},R=B.recommendations||{{}},Q=B.data_quality||{{}},P=B.provenance||{{}};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const typed=(container,id)=>{{const m=(container||{{}})[id]||{{}};return m.state==='VALID'?m.value:null}};
const money=v=>v==null?'—':`${{v}} RUB`;
const result=C.results||{{}};
const cards=[
 ['Статус',B.run_status],
 ['Чистая прибыль',money(typed(result,'net_profit_amount'))],
 ['Прибыль на единицу',money(typed(result,'profit_per_sold_unit'))],
 ['Рентабельность',typed(result,'profitability_of_costs')??'—'],
 ['Продано единиц',typed(result,'net_sold_units')??'—'],
 ['Сверка',B.reconciliation?.state||'—'],
 ['Рекомендации',R.recommendation_count??0],
 ['Блокирующие метрики',(Q.blocked_metrics||[]).length],
 ['Пакет',B.bundle_hash.slice(0,16)+'…']
];
document.getElementById('summary').innerHTML=cards.map(x=>`<div class="card"><div class="key">${{esc(x[0])}}</div><div class="value">${{esc(x[1])}}</div></div>`).join('');
const moneyIds=['gross_sales_amount','payout_amount','marketplace_commission_amount','forward_logistics_amount','reverse_logistics_amount','storage_amount','advertising_amount','fines_withholdings_amount','product_cost_amount','other_expense_amount','tax_amount','net_profit_amount'];
const combined={{...(A.observed_metrics||{{}}),...(result||{{}})}};
const chart=moneyIds.map(id=>[id,Number(typed(combined,id))]).filter(x=>Number.isFinite(x[1]));
const max=Math.max(1,...chart.map(x=>Math.abs(x[1])));
document.getElementById('financial-chart').innerHTML=chart.length?chart.map(([id,value])=>`<div class="bar-row"><div>${{esc(id)}}</div><div class="bar-track"><div class="bar-fill" style="width:${{Math.max(1,Math.abs(value)/max*100).toFixed(2)}}%"></div></div><div class="${{value<0?'negative':value>0?'positive':''}}">${{esc(value)}}</div></div>`).join(''):'<div class="muted">Финансовые метрики недоступны.</div>';
const boundary=m=>Array.isArray(m.expense_boundary)?m.expense_boundary.join(' | '):'';
document.getElementById('finance').innerHTML=Object.keys(result).sort().map(id=>{{const m=result[id]||{{}};return `<tr><td>${{esc(id)}}</td><td>${{esc(m.state)}}</td><td>${{esc(m.value)}}</td><td>${{esc(m.currency)}}</td><td>${{esc(m.accounting_view)}}</td><td>${{esc(boundary(m))}}</td></tr>`}}).join('');
const metrics=A.observed_metrics||{{}};
function renderMetrics(){{const q=document.getElementById('metric-search').value.toLowerCase();document.getElementById('metrics').innerHTML=Object.keys(metrics).sort().filter(id=>!q||id.toLowerCase().includes(q)||JSON.stringify(metrics[id]).toLowerCase().includes(q)).map(id=>{{const m=metrics[id]||{{}};return `<tr><td>${{esc(id)}}</td><td>${{esc(m.state)}}</td><td>${{esc(m.value)}}</td><td>${{esc(m.unit)}}</td><td>${{esc(m.currency)}}</td><td>${{esc(m.reason_code)}}</td></tr>`}}).join('')}}
document.getElementById('metric-search').addEventListener('input',renderMetrics);renderMetrics();
const items=Array.isArray(R.recommendations)?R.recommendations:[];
const categories=[...new Set(items.map(x=>x.category).filter(Boolean))].sort();document.getElementById('category').innerHTML+=categories.map(x=>`<option>${{esc(x)}}</option>`).join('');
function effect(e){{if(!e)return '—';if(e.amount!=null)return `${{e.amount}} ${{e.currency||''}}`;if(e.value!=null)return `${{e.value}} ${{e.currency||''}}`;if(e.amount_min!=null||e.amount_max!=null)return `${{e.amount_min??'—'}}…${{e.amount_max??'—'}} ${{e.currency||''}}`;return e.reason_code||e.state||'—'}}
function renderRecommendations(){{const q=document.getElementById('search').value.toLowerCase(),s=document.getElementById('severity').value,p=document.getElementById('priority').value,c=document.getElementById('category').value;const rows=items.filter(x=>(!s||x.severity===s)&&(!p||x.priority_dimension===p)&&(!c||x.category===c)&&(!q||JSON.stringify(x).toLowerCase().includes(q)));document.getElementById('recommendations').innerHTML=rows.map(x=>`<tr><td><span class="badge ${{esc(x.severity)}}">${{esc(x.severity)}}</span></td><td>${{esc(x.priority_dimension)}}</td><td>${{esc(x.category)}}</td><td>${{esc(x.action||x.action_code)}}</td><td>${{esc(x.reason)}}</td><td>${{esc(effect(x.current_effect))}}</td><td>${{esc(effect(x.forecast_effect_min||x.forecast_effect))}}</td><td>${{esc(effect(x.forecast_effect_max||x.forecast_effect))}}</td><td>${{esc(x.confidence_level||x.confidence?.state)}}</td><td>${{esc((x.evidence_refs||[]).join(' | '))}}</td><td>${{esc((x.limitations||[]).join(' | '))}}</td></tr>`).join('')}}
['search','severity','priority','category'].forEach(id=>document.getElementById(id).addEventListener(id==='search'?'input':'change',renderRecommendations));renderRecommendations();
const quality=[['Admission',Q.admission_state],['Storage zone',Q.storage_zone_state],['Source bridge',Q.source_bridge_status],['Finance request',Q.finance_request_state],['Blocked metrics',(Q.blocked_metrics||[]).join(' | ')||'—'],['Reason codes',(Q.reason_codes||[]).join(' | ')||'—']];document.getElementById('quality').innerHTML=quality.map(x=>`<div class="card"><div class="key">${{esc(x[0])}}</div><div>${{esc(x[1])}}</div></div>`).join('');
document.getElementById('limitations').innerHTML=(B.limitations||[]).map(x=>`<li>${{esc(x)}}</li>`).join('');
const controls=[['Bundle SHA-256',B.bundle_hash],['Source SHA-256',B.source_sha256],['Generated',B.generated_at],['Calculation result SHA-256',P.calculation?.result_hash||'—'],['Recommendation bundle SHA-256',P.recommendations?.bundle_hash||'—'],['Canonical rows SHA-256',P.source?.canonical_rows_sha256||'—'],['Canonical ledger SHA-256',P.source?.canonical_ledger_sha256||'—'],['Marketplace writes',P.runtime?.marketplace_write_enabled]];document.getElementById('control').innerHTML=controls.map(x=>`<div class="card"><div class="key">${{esc(x[0])}}</div><code>${{esc(x[1])}}</code></div>`).join('');
</script>
</body>
</html>'''
    return document.encode("utf-8")
