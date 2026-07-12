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
const COSTS = FINANCIAL.filter(item=>item[2]==='expense');
const COST_COLORS = ['var(--chart-1)','var(--chart-2)','var(--chart-3)','var(--chart-4)','var(--chart-5)','var(--chart-6)','var(--chart-7)','var(--chart-8)','var(--chart-9)'];
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
const signedMoney = value => value==null?'—':`${value>0?'+':''}${money(value)}`;
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
const badge = (value,label) => { const shown=label!==undefined&&label!==null&&label!==''?label:(value!==undefined&&value!==null&&value!==''?value:'NOT_AVAILABLE'); return el('span',badgeClass(value),shown); };
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
  const reduced=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  window.scrollTo({top:0,behavior:reduced?'auto':'smooth'});
}
const dashboardTabs=[...document.querySelectorAll('.nav-tab')];
dashboardTabs.forEach((node,index)=>{
  node.addEventListener('click',()=>setView(node.dataset.view));
  node.addEventListener('keydown',event=>{
    const key=event.key; if(!['ArrowLeft','ArrowRight','Home','End'].includes(key)) return;
    event.preventDefault();
    const target=key==='Home'?0:key==='End'?dashboardTabs.length-1:(index+(key==='ArrowRight'?1:-1)+dashboardTabs.length)%dashboardTabs.length;
    setView(dashboardTabs[target].dataset.view);
  });
});
document.querySelectorAll('[data-go-view]').forEach(node=>node.addEventListener('click',()=>setView(node.dataset.goView)));
$('reload-button').addEventListener('click',()=>window.location.reload());
$('print-button').addEventListener('click',()=>window.print());

function kpiCard(label,value,note,semantic){
  const card=el('article',`kpi-card kpi-${semantic}`);
  append(card,el('div','kpi-label',label),el('div','kpi-value',value),el('div','kpi-note',note)); return card;
}
function decisionSignal(profit){
  const blocked=(Q.blocked_metrics||[]).length;
  const critical=RECOMMENDATIONS.filter(item=>item.severity==='CRITICAL').length;
  const high=RECOMMENDATIONS.filter(item=>item.severity==='HIGH').length;
  if(blocked>0 || critical>0) return {state:'critical',title:`Требуют устранения: ${blocked+critical}`,text:'Есть блокирующие метрики или критические рекомендации. Финансовые выводы необходимо проверить до управленческого решения.'};
  if(profit!==null && profit<0) return {state:'critical',title:'Прибыль отрицательная — восстановите безубыточность',text:'Начните с крупнейших подтверждённых расходов и рекомендаций с приоритетом «Прибыль».'};
  if(high>0) return {state:'warning',title:`Высокий приоритет: ${high}`,text:'Критических блокеров нет, но есть действия с высоким приоритетом. Проверьте evidence и прогноз перед подтверждением сценария.'};
  return {state:'good',title:'Расчёт готов к управленческой проверке',text:'Обязательные контуры не сообщают о критических блокерах. Quantum по-прежнему не выполняет действия автоматически.'};
}
function renderDecisionBanner(profit){
  const signal=decisionSignal(profit); const banner=$('decision-banner');
  banner.className=`decision-banner state-${signal.state}`;
  $('decision-banner-title').textContent=signal.title; $('decision-banner-text').textContent=signal.text;
  const badges=$('decision-banner-badges'); clear(badges);
  append(badges,badge(B.run_status||'NOT_AVAILABLE'),badge(B.reconciliation?.state||'NOT_AVAILABLE'),badge(C.publication_state||'NOT_AVAILABLE'),badge(P.runtime?.marketplace_write_enabled===true?'ENABLED':'DISABLED','Marketplace writes: disabled'));
  const header=$('decision-state'); header.className=`header-state state-${signal.state}`; header.textContent=signal.state==='critical'?'Требуется внимание':signal.state==='warning'?'Высокий приоритет':'Данные готовы';
}
function renderReadiness(){
  const checks=[
    ['Admission',Q.admission_state==='ADMITTED'],
    ['Finance request',Q.finance_request_state==='READY'],
    ['Reconciliation',B.reconciliation?.state==='RECONCILED'],
    ['Нет blocked metrics',(Q.blocked_metrics||[]).length===0],
    ['Marketplace writes disabled',P.runtime?.marketplace_write_enabled!==true]
  ];
  const passed=checks.filter(item=>item[1]).length;
  const score=Math.round(passed/checks.length*100);
  const root=$('decision-readiness'); root.setAttribute('aria-valuenow',String(score)); root.style.setProperty('--readiness',`${score}%`);
  $('decision-readiness-value').textContent=`${score}%`; $('decision-readiness-bar').style.width=`${score}%`;
  $('decision-readiness-label').textContent=score===100?'Все обязательные evidence-gates пройдены':`Пройдено ${passed} из ${checks.length} gates`;
  const list=$('decision-readiness-checks'); clear(list);
  checks.forEach(([label,ok])=>{const item=el('li',ok?'check-pass':'',`${label}: ${ok?'PASS':'CHECK'}`);list.appendChild(item);});
}
function renderFinancialChart(){
  const combined={...OBSERVED,...RESULTS};
  const values=FINANCIAL.map(([id,label,type])=>({id,label,type,value:metricValue(combined,id)})).filter(item=>item.value!==null);
  const visual=values.map(item=>({...item,signed:item.type==='expense'?-Math.abs(item.value):item.value}));
  const max=Math.max(1,...visual.map(item=>Math.abs(item.signed)));
  const chart=$('financial-chart'); clear(chart);
  if(!visual.length){append(chart,el('div','empty-state','Финансовые метрики недоступны.'));return;}
  visual.forEach(item=>{
    const row=el('div','chart-row');
    const label=el('div','chart-label',item.label);
    const track=el('div','chart-track'); track.setAttribute('role','img'); track.setAttribute('aria-label',`${item.label}: ${signedMoney(item.signed)}`);
    const zero=el('span','chart-zero'); zero.setAttribute('aria-hidden','true');
    const resultClass=item.type==='result'?(item.signed<0?'result-negative':'result-positive'):item.type;
    const direction=item.signed<0?'negative':'positive';
    const fill=el('span',`chart-fill chart-fill-${direction} chart-${resultClass}`); fill.setAttribute('aria-hidden','true');
    fill.style.width=`${Math.max(1,Math.abs(item.signed)/max*50).toFixed(2)}%`;
    append(track,zero,fill);
    const value=el('div',`chart-value ${item.signed<0?'text-negative':'text-positive'}`,signedMoney(item.signed));
    append(row,label,track,value); chart.appendChild(row);
  });
}
function renderCostComposition(){
  const combined={...OBSERVED,...RESULTS};
  const costs=COSTS.map(([id,label])=>({id,label,value:metricValue(combined,id)})).filter(item=>item.value!==null&&item.value>0);
  const root=$('cost-composition-chart'); clear(root);
  const total=costs.reduce((sum,item)=>sum+item.value,0);
  if(!costs.length || total<=0){append(root,el('div','empty-state','Подтверждённые расходы для структуры недоступны.'));return;}
  let cursor=0; const stops=[];
  costs.forEach((item,index)=>{const start=cursor;cursor+=item.value/total*100;stops.push(`${COST_COLORS[index%COST_COLORS.length]} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`);});
  const donut=el('div','donut'); donut.style.background=`conic-gradient(${stops.join(',')})`; donut.setAttribute('role','img'); donut.setAttribute('aria-label',`Структура расходов. Всего ${money(total)}. ${costs.map(item=>`${item.label}: ${(item.value/total*100).toFixed(1)}%`).join('; ')}`);
  const center=el('div','donut-center'); append(center,el('strong','',money(total)),el('span','','всего расходов')); donut.appendChild(center);
  const legend=el('div','donut-legend');
  costs.forEach((item,index)=>{const row=el('div','donut-row');const dot=el('span',`donut-dot cost-color-${index%COST_COLORS.length}`);dot.setAttribute('aria-hidden','true');const share=item.value/total*100;append(row,dot,el('span','donut-label',item.label),el('span','donut-value',`${money(item.value)} · ${share.toFixed(1)}%`));legend.appendChild(row);});
  append(root,donut,legend);
}
function renderPriorityDistribution(){
  const root=$('priority-chart'); clear(root);
  const rows=[['PROFIT','Прибыль','priority-profit'],['SUSTAINABLE_GROWTH','Устойчивый рост','priority-growth'],['TURNOVER','Оборот','priority-turnover']].map(([id,label,className])=>({id,label,className,count:RECOMMENDATIONS.filter(item=>item.priority_dimension===id).length}));
  const max=Math.max(1,...rows.map(item=>item.count));
  rows.forEach(item=>{const row=el('div','priority-bar-row');const track=el('div','priority-bar-track');const fill=el('div',`priority-bar-fill ${item.className}`);fill.style.width=`${item.count===0?0:Math.max(4,item.count/max*100).toFixed(2)}%`;track.setAttribute('role','img');track.setAttribute('aria-label',`${item.label}: ${item.count}`);track.appendChild(fill);append(row,el('div','priority-bar-label',item.label),track,el('div','priority-bar-value',item.count));root.appendChild(row);});
}
function svgNode(tag,attributes){const node=document.createElementNS('http'+'://www.w3.org/2000/svg',tag);Object.entries(attributes||{}).forEach(([key,value])=>node.setAttribute(key,String(value)));return node;}
function renderHistory(){
  const root=$('history-chart'); clear(root);
  const raw=Array.isArray(A.time_series)?A.time_series:[];
  const points=raw.map(item=>({period:text(item.period),value:number(item.net_profit_amount)})).filter(item=>item.period!=='—'&&item.value!==null);
  if(points.length<2){
    const empty=el('div','history-empty'); append(empty,el('strong','','Недостаточно исторических данных'),el('p','','Quantum не строит фиктивный тренд по одному периоду. Загрузите минимум два сопоставимых подтверждённых периода.'),el('span','history-code','NO_HISTORICAL_SERIES')); root.appendChild(empty); return;
  }
  const width=620,height=220,pad=34; const values=points.map(item=>item.value); const min=Math.min(0,...values),max=Math.max(0,...values); const span=Math.max(1,max-min);
  const x=index=>pad+(width-pad*2)*(points.length===1?0:index/(points.length-1)); const y=value=>height-pad-(value-min)/span*(height-pad*2);
  const svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`,class:'history-svg',role:'img','aria-label':`История чистой прибыли: ${points.map(item=>`${item.period} ${money(item.value)}`).join('; ')}`});
  [0,.25,.5,.75,1].forEach(ratio=>{const gy=pad+ratio*(height-pad*2);svg.appendChild(svgNode('line',{x1:pad,y1:gy,x2:width-pad,y2:gy,class:'history-grid-line'}));});
  if(min<=0&&max>=0){svg.appendChild(svgNode('line',{x1:pad,y1:y(0),x2:width-pad,y2:y(0),class:'history-zero-line'}));}
  const polyline=svgNode('polyline',{points:points.map((item,index)=>`${x(index)},${y(item.value)}`).join(' '),class:'history-line'});svg.appendChild(polyline);
  points.forEach((item,index)=>{const circle=svgNode('circle',{cx:x(index),cy:y(item.value),r:5,class:'history-point'});const title=svgNode('title');title.textContent=`${item.period}: ${money(item.value)}`;circle.appendChild(title);svg.appendChild(circle);const label=svgNode('text',{x:x(index),y:height-10,'text-anchor':'middle',class:'history-axis-label'});label.textContent=item.period;svg.appendChild(label);});
  root.appendChild(svg);
}
function renderPriorityActions(){
  const top=[...RECOMMENDATIONS].sort((a,b)=>(SEVERITY_ORDER[a.severity]??9)-(SEVERITY_ORDER[b.severity]??9)||(PRIORITY_ORDER[a.priority_dimension]??9)-(PRIORITY_ORDER[b.priority_dimension]??9)||actionLabel(a).localeCompare(actionLabel(b),'ru')).slice(0,5);
  const actions=$('priority-actions'); clear(actions);
  if(!top.length){append(actions,el('div','empty-state','Активных рекомендаций нет.'));return;}
  top.forEach((item,index)=>{const row=el('div','rec-summary-row');const rank=el('span','rec-rank',String(index+1).padStart(2,'0'));const btn=el('button','rec-summary-button',actionLabel(item));btn.type='button';btn.addEventListener('click',()=>openRecommendation(item,btn));append(row,rank,btn,badge(item.severity,severityLabel(item)));actions.appendChild(row);});
}
function renderOverviewStatus(){
  const statusItems=[
    ['Статус запуска',B.run_status],['Admission',Q.admission_state],['Source bridge',Q.source_bridge_status],
    ['Finance request',Q.finance_request_state],['Reconciliation',B.reconciliation?.state],['Publication',C.publication_state||'NOT_AVAILABLE'],
    ['Blocked metrics',(Q.blocked_metrics||[]).length],['Marketplace writes',P.runtime?.marketplace_write_enabled===true?'ENABLED':'DISABLED'],['Bundle',text(B.bundle_hash).slice(0,16)+'…']
  ];
  const grid=$('overview-status'); clear(grid);
  statusItems.forEach(([label,value])=>{const card=el('article','status-card');append(card,el('div','status-label',label),append(el('div','status-value'),badge(value)));grid.appendChild(card);});
}
function renderOverview(){
  $('header-dataset').textContent=`Набор: ${text(B.dataset_id)}`;
  $('header-generated').textContent=`Сформирован: ${text(B.generated_at)}`;
  $('header-source').textContent=`Источник: ${text(B.source_type)}`;
  const profit=metricValue(RESULTS,'net_profit_amount');
  const perUnit=metricValue(RESULTS,'profit_per_sold_unit');
  const roi=metricValue(RESULTS,'profitability_of_costs');
  const sold=metricValue(RESULTS,'net_sold_units');
  renderDecisionBanner(profit);
  const kpis=$('kpi-grid'); clear(kpis);
  append(kpis,
    kpiCard('Чистая прибыль',money(profit),'После подтверждённых governed расходов',profit==null?'neutral':profit<0?'negative':'positive'),
    kpiCard('Прибыль на единицу',money(perUnit),'На одну проданную единицу',perUnit==null?'neutral':perUnit<0?'negative':'positive'),
    kpiCard('Рентабельность',roi==null?'—':format(roi,'RATIO'),'Отношение прибыли к подтверждённым затратам',roi==null?'neutral':roi<0?'negative':'positive'),
    kpiCard('Продано единиц',sold==null?'—':format(sold,'ITEM'),'Net sold units после возвратов',sold==null?'neutral':'neutral')
  );
  renderPriorityActions(); renderReadiness(); renderFinancialChart(); renderCostComposition(); renderPriorityDistribution(); renderHistory(); renderOverviewStatus();
}

"""
