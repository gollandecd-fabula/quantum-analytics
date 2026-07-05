from __future__ import annotations

DASHBOARD_JS_CORE = r"""
'use strict';
const bundleNode = document.getElementById('bundle-data');
const B = JSON.parse(bundleNode.textContent);
const A = B.analysis || {};
const C = B.calculation || {};
const R = B.recommendations || {};
const Q = B.data_quality || {};
const P = B.provenance || {};
const RESULTS = C.results || {};
const OBSERVED = A.observed_metrics || {};
const RECOMMENDATIONS = Array.isArray(R.recommendations) ? R.recommendations : [];
const SEVERITY_ORDER = {CRITICAL:0,HIGH:1,MEDIUM:2,LOW:3};
const PRIORITY_ORDER = {PROFIT:0,SUSTAINABLE_GROWTH:1,TURNOVER:2};
const ACTION_LABELS = {COMPLETE_REQUIRED_INPUTS:'Заполнить обязательные данные',INVESTIGATE_LOW_BUYOUT:'Разобрать низкий выкуп',REVIEW_STOCKOUT:'Проверить дефицит остатка',REVIEW_STOCK_WITHOUT_BUYOUT:'Проверить остаток без выкупа',REVIEW_HIGH_STOCK_TO_BUYOUT_RATIO:'Проверить избыточный остаток',INVESTIGATE_HIGH_RETURN_RATE:'Разобрать высокий уровень возвратов',REVIEW_COMMISSION_AND_PRICE_STRUCTURE:'Проверить комиссию и цену',REVIEW_FORWARD_LOGISTICS_COST:'Проверить прямую логистику',REVIEW_REVERSE_LOGISTICS_COST:'Проверить обратную логистику',REVIEW_STORAGE_COST:'Проверить стоимость хранения',RECONCILE_SETTLEMENT_GAP:'Сверить расхождение выплаты',RESTORE_BREAK_EVEN:'Восстановить безубыточность',RESOLVE_RECONCILIATION_CONFLICT:'Устранить конфликт сверки'};
const CATEGORY_LABELS = {DATA_QUALITY:'Качество данных',SALES:'Продажи',INVENTORY:'Остатки',RETURNS:'Возвраты',COST:'Расходы',LOGISTICS:'Логистика',RECONCILIATION:'Сверка',FINANCIAL:'Финансы',ADVERTISING:'Реклама',STORAGE:'Хранение'};
const PRIORITY_LABELS = {PROFIT:'Прибыль',SUSTAINABLE_GROWTH:'Устойчивый рост',TURNOVER:'Оборот'};
const SEVERITY_LABELS = {CRITICAL:'Критическая',HIGH:'Высокая',MEDIUM:'Средняя',LOW:'Низкая'};
const FINANCIAL = [
  ['gross_sales_amount','Валовые продажи','income'],
  ['payout_amount','Выплата маркетплейса','income'],
  ['marketplace_commission_amount','Комиссия маркетплейса','expense'],
  ['forward_logistics_amount','Прямая логистика','expense'],
  ['reverse_logistics_amount','Обратная логистика','expense'],
  ['storage_amount','Хранение','expense'],
  ['advertising_amount','Реклама','expense'],
  ['fines_withholdings_amount','Штрафы и удержания','expense'],
  ['product_cost_amount','Себестоимость товара','expense'],
  ['other_expense_amount','Прочие расходы','expense'],
  ['tax_amount','Налог','expense'],
  ['net_profit_amount','Чистая прибыль','result']
];
const state = {view:'overview',rec:{query:'',severity:'',priority:'',category:'',sort:'severity'},metric:{query:'',scope:'',state:'',unit:'',sort:'id'},lastFocus:null};
const $ = id => document.getElementById(id);
const text = value => value == null || value === '' ? '—' : String(value);
const number = value => { const n=Number(value); return Number.isFinite(n)?n:null; };
const metricValue = (container,id) => { const m=(container||{})[id]||{}; return m.state==='VALID'?number(m.value):null; };
const metricById = id => RESULTS[id] || OBSERVED[id] || null;
const format = (value,unit,currency) => {
  const n=number(value); if(n===null) return text(value);
  const u=String(unit||'').toUpperCase();
  if(u==='RATIO'||u==='PERCENT'||u==='RATE') return new Intl.NumberFormat('ru-RU',{style:'percent',minimumFractionDigits:2,maximumFractionDigits:2}).format(n);
  if(currency) return new Intl.NumberFormat('ru-RU',{style:'currency',currency:String(currency),minimumFractionDigits:2,maximumFractionDigits:2}).format(n);
  if(['ITEM','COUNT','UNITS'].includes(u)) return new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(n);
  return new Intl.NumberFormat('ru-RU',{maximumFractionDigits:4}).format(n);
};
const money = value => value==null?'—':new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',minimumFractionDigits:2,maximumFractionDigits:2}).format(value);
const el = (tag,className,value) => { const node=document.createElement(tag); if(className) node.className=className; if(value!==undefined) node.textContent=text(value); return node; };
const clear = node => { while(node.firstChild) node.removeChild(node.firstChild); };
const append = (parent,...children) => { children.flat().filter(Boolean).forEach(child=>parent.appendChild(child)); return parent; };
const badgeClass = value => {
  const v=String(value||'').toUpperCase();
  if(['CRITICAL','CONFLICT','ERROR','REJECTED','BLOCKED','INVALID'].includes(v)) return 'badge badge-critical';
  if(['HIGH','PENDING','WARNING','PARTIAL'].includes(v)) return 'badge badge-high';
  if(['MEDIUM','PILOT','NOT_REQUESTED'].includes(v)) return 'badge badge-medium';
  if(['VALID','READY','RECONCILED','ADMITTED','COMPLETE','PILOT_RUN_COMPLETE'].includes(v)) return 'badge badge-good';
  return 'badge badge-neutral';
};
const badge = (value,label) => el('span',badgeClass(value),label||value||'NOT_AVAILABLE');
const actionLabel = item => ACTION_LABELS[item.action_code] || item.action || item.action_code || 'Без действия';
const categoryLabel = item => CATEGORY_LABELS[item.category] || item.category || 'Без категории';
const priorityLabel = item => PRIORITY_LABELS[item.priority_dimension] || item.priority_dimension || 'Без цели';
const severityLabel = item => SEVERITY_LABELS[item.severity] || item.severity || 'Без срочности';
const reasonLabel = item => item.reason || 'Причина не указана';
const effectText = effect => {
  if(!effect || typeof effect!=='object') return '—';
  const currency=effect.currency||'';
  if(effect.amount!=null) return format(effect.amount,'MONEY',currency);
  if(effect.value!=null) return format(effect.value,effect.unit,currency);
  if(effect.amount_min!=null||effect.amount_max!=null) return `${text(effect.amount_min)} … ${text(effect.amount_max)} ${currency}`.trim();
  return effect.reason_code || effect.state || '—';
};
const safeCsv = value => { let s=text(value).replaceAll('"','""'); if(/^[=+\-@]/.test(s)) s="'"+s; return `"${s}"`; };
let toastTimer;
function toast(message){ const node=$('toast'); node.textContent=message; node.classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>node.classList.remove('show'),2200); }
function setView(name){
  if(document.body.classList.contains('drawer-open')) closeDrawer();
  state.view=name;
  document.querySelectorAll('.view').forEach(node=>node.hidden=node.id!==`view-${name}`);
  document.querySelectorAll('.nav-tab').forEach(node=>node.setAttribute('aria-selected',String(node.dataset.view===name)));
  const tab=$(`tab-${name}`); if(tab) tab.focus({preventScroll:true});
  window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('.nav-tab').forEach(node=>node.addEventListener('click',()=>setView(node.dataset.view)));
document.querySelectorAll('[data-go-view]').forEach(node=>node.addEventListener('click',()=>setView(node.dataset.goView)));
$('reload-button').addEventListener('click',()=>window.location.reload());
$('print-button').addEventListener('click',()=>window.print());

function kpiCard(label,value,note,semantic){
  const card=el('article',`kpi-card kpi-${semantic}`);
  append(card,el('div','kpi-label',label),el('div','kpi-value',value),el('div','kpi-note',note)); return card;
}
function renderOverview(){
  $('header-dataset').textContent=`Набор: ${text(B.dataset_id)}`;
  $('header-generated').textContent=`Сформирован: ${text(B.generated_at)}`;
  $('header-source').textContent=`Источник: ${text(B.source_type)}`;
  const profit=metricValue(RESULTS,'net_profit_amount');
  const perUnit=metricValue(RESULTS,'profit_per_sold_unit');
  const roi=metricValue(RESULTS,'profitability_of_costs');
  const sold=metricValue(RESULTS,'net_sold_units');
  const kpis=$('kpi-grid'); clear(kpis);
  append(kpis,
    kpiCard('Чистая прибыль',money(profit),'После учтённых governed расходов',profit==null?'neutral':profit<0?'negative':'positive'),
    kpiCard('Прибыль на единицу',money(perUnit),'На одну проданную единицу',perUnit==null?'neutral':perUnit<0?'negative':'positive'),
    kpiCard('Рентабельность',roi==null?'—':format(roi,'RATIO'),'Отношение прибыли к затратам',roi==null?'neutral':roi<0?'negative':'positive'),
    kpiCard('Продано единиц',sold==null?'—':format(sold,'ITEM'),'Net sold units',sold==null?'neutral':'neutral')
  );
  const combined={...OBSERVED,...RESULTS};
  const values=FINANCIAL.map(([id,label,type])=>({id,label,type,value:metricValue(combined,id)})).filter(x=>x.value!==null);
  const max=Math.max(1,...values.map(x=>Math.abs(x.value)));
  const chart=$('financial-chart'); clear(chart);
  if(!values.length) append(chart,el('div','empty-state','Финансовые метрики недоступны.'));
  values.forEach(item=>{
    const row=el('div','chart-row'); const label=el('div','chart-label',item.label);
    const track=el('div','chart-track'); const fill=el('div',`chart-fill chart-${item.type==='result'?(item.value<0?'result-negative':'result-positive'):item.type}`);
    fill.style.width=`${Math.max(1,Math.abs(item.value)/max*100).toFixed(2)}%`; track.appendChild(fill);
    append(row,label,track,el('div',`chart-value ${item.value<0?'text-negative':item.type==='result'?'text-positive':''}`,money(item.value))); chart.appendChild(row);
  });
  const top=[...RECOMMENDATIONS].sort((a,b)=>(SEVERITY_ORDER[a.severity]??9)-(SEVERITY_ORDER[b.severity]??9)).slice(0,5);
  const actions=$('priority-actions'); clear(actions);
  if(!top.length) append(actions,el('div','empty-state','Активных рекомендаций нет.'));
  top.forEach((item,index)=>{
    const row=el('div','rec-summary-row'); const left=el('div'); append(left,badge(item.severity,severityLabel(item)));
    const btn=el('button','rec-summary-button',actionLabel(item)); btn.type='button'; btn.addEventListener('click',()=>openRecommendation(item,btn));
    append(left,btn); append(row,left,el('span','',String(index+1))); actions.appendChild(row);
  });
  const calc=C||{};
  const statusItems=[
    ['Статус запуска',B.run_status],['Admission',Q.admission_state],['Source bridge',Q.source_bridge_status],
    ['Finance request',Q.finance_request_state],['Reconciliation',B.reconciliation?.state],['Publication',calc.publication_state||'NOT_AVAILABLE'],
    ['Blocked metrics',(Q.blocked_metrics||[]).length],['Marketplace writes',P.runtime?.marketplace_write_enabled===true?'ENABLED':'DISABLED'],['Bundle',B.bundle_hash.slice(0,16)+'…']
  ];
  const grid=$('overview-status'); clear(grid);
  statusItems.forEach(([label,value])=>{ const card=el('article','status-card'); append(card,el('div','status-label',label),el('div','status-value',value)); grid.appendChild(card); });
}

"""
