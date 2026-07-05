from __future__ import annotations

DASHBOARD_JS_DATA = r"""
function populateSelect(id,values){ const select=$(id); [...new Set(values.filter(Boolean).map(String))].sort().forEach(value=>{ const option=el('option','',value); option.value=value; select.appendChild(option); }); }
function recSearchText(item){ return JSON.stringify(item).toLocaleLowerCase('ru-RU'); }
function filteredRecommendations(){
  const q=state.rec.query.trim().toLocaleLowerCase('ru-RU');
  const rows=RECOMMENDATIONS.filter(item=>(!q||recSearchText(item).includes(q))&&(!state.rec.severity||item.severity===state.rec.severity)&&(!state.rec.priority||item.priority_dimension===state.rec.priority)&&(!state.rec.category||item.category===state.rec.category));
  const cmp={
    severity:(a,b)=>(SEVERITY_ORDER[a.severity]??9)-(SEVERITY_ORDER[b.severity]??9)||actionLabel(a).localeCompare(actionLabel(b),'ru'),
    priority:(a,b)=>(PRIORITY_ORDER[a.priority_dimension]??9)-(PRIORITY_ORDER[b.priority_dimension]??9)||actionLabel(a).localeCompare(actionLabel(b),'ru'),
    category:(a,b)=>text(a.category).localeCompare(text(b.category),'ru')||actionLabel(a).localeCompare(actionLabel(b),'ru'),
    action:(a,b)=>actionLabel(a).localeCompare(actionLabel(b),'ru')
  }[state.rec.sort];
  return rows.sort(cmp);
}
function effectCell(label,effect){ const cell=el('div','effect-cell'); append(cell,el('span','effect-label',label),el('span','effect-value',effectText(effect))); return cell; }
function recommendationCard(item){
  const card=el('article','recommendation-card');
  const head=el('div','rec-head'), badges=el('div','rec-badges'); append(badges,badge(item.severity,severityLabel(item)),badge(item.priority_dimension,priorityLabel(item)),badge(item.category,categoryLabel(item)));
  const detail=el('button','button button-quiet button-small','Подробнее'); detail.type='button'; detail.addEventListener('click',()=>openRecommendation(item,detail)); append(head,badges,detail);
  const foot=el('div','rec-foot'); append(foot,el('span','',`Уверенность: ${text(item.confidence_level||item.confidence?.state)}`),el('span','',`Evidence: ${(item.evidence_refs||[]).length}`));
  append(card,head,el('h3','rec-title',actionLabel(item)),el('div','rec-reason',reasonLabel(item)),append(el('div','effect-grid'),effectCell('Текущий эффект',item.current_effect),effectCell('Прогноз min',item.forecast_effect_min||item.forecast_effect),effectCell('Прогноз max',item.forecast_effect_max||item.forecast_effect)),foot);
  return card;
}
function renderRecommendations(){
  const rows=filteredRecommendations(); const grid=$('recommendation-grid'); clear(grid);
  rows.forEach(item=>grid.appendChild(recommendationCard(item)));
  $('rec-empty').hidden=rows.length!==0; $('rec-result-count').textContent=`Показано ${rows.length} из ${RECOMMENDATIONS.length}`;
}
function bindRecFilters(){
  populateSelect('category',RECOMMENDATIONS.map(x=>x.category));
  const bindings=[['rec-search','query','input'],['severity','severity','change'],['priority','priority','change'],['category','category','change'],['rec-sort','sort','change']];
  bindings.forEach(([id,key,event])=>$(id).addEventListener(event,e=>{state.rec[key]=e.target.value;renderRecommendations();}));
  $('rec-reset').addEventListener('click',()=>{state.rec={query:'',severity:'',priority:'',category:'',sort:'severity'}; bindings.forEach(([id,key])=>$(id).value=state.rec[key]); renderRecommendations();});
  $('rec-export').addEventListener('click',exportRecommendations);
}
function exportRecommendations(){
  const rows=filteredRecommendations();
  const header=['severity','priority','category','action','reason','current_effect','forecast_min','forecast_max','confidence','evidence','limitations'];
  const data=[header,...rows.map(item=>[item.severity,item.priority_dimension,item.category,actionLabel(item),reasonLabel(item),effectText(item.current_effect),effectText(item.forecast_effect_min||item.forecast_effect),effectText(item.forecast_effect_max||item.forecast_effect),item.confidence_level||item.confidence?.state,(item.evidence_refs||[]).join(' | '),(item.limitations||[]).join(' | ')])];
  const csv='\uFEFF'+data.map(row=>row.map(safeCsv).join(';')).join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}); const url=URL.createObjectURL(blob); const link=document.createElement('a');
  link.href=url; link.download=`quantum_recommendations_${B.dataset_id}.csv`; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url); toast(`Экспортировано: ${rows.length}`);
}

const METRICS=[...Object.entries(OBSERVED).map(([id,m])=>({id,scope:'SOURCE',...m})),...Object.entries(RESULTS).map(([id,m])=>({id,scope:'CALCULATION',...m}))];
function metricSearchText(item){ return JSON.stringify(item).toLocaleLowerCase('ru-RU'); }
function filteredMetrics(){
  const q=state.metric.query.trim().toLocaleLowerCase('ru-RU');
  const rows=METRICS.filter(item=>(!q||metricSearchText(item).includes(q))&&(!state.metric.scope||item.scope===state.metric.scope)&&(!state.metric.state||item.state===state.metric.state)&&(!state.metric.unit||item.unit===state.metric.unit));
  const numericValue=item=>number(item.value)??Number.NEGATIVE_INFINITY;
  const cmp={id:(a,b)=>a.id.localeCompare(b.id),scope:(a,b)=>a.scope.localeCompare(b.scope)||a.id.localeCompare(b.id),state:(a,b)=>text(a.state).localeCompare(text(b.state))||a.id.localeCompare(b.id),'value-desc':(a,b)=>numericValue(b)-numericValue(a),'value-asc':(a,b)=>numericValue(a)-numericValue(b)}[state.metric.sort];
  return rows.sort(cmp);
}
function renderMetrics(){
  const rows=filteredMetrics(), body=$('metric-table-body'); clear(body);
  rows.forEach(item=>{
    const tr=document.createElement('tr');
    const cells=[item.scope,item.id,item.state,format(item.value,item.unit,item.currency),item.unit,item.currency,item.reason_code];
    cells.forEach((value,index)=>{ const td=el('td',index===1?'metric-id':index===3?'numeric':'',value); if(index===2){clear(td);td.appendChild(badge(value));} tr.appendChild(td); });
    const actionTd=document.createElement('td'), button=el('button','row-action','Детали'); button.type='button'; button.addEventListener('click',()=>openMetric(item,button)); actionTd.appendChild(button); tr.appendChild(actionTd); body.appendChild(tr);
  });
  $('metric-empty').hidden=rows.length!==0; $('metric-result-count').textContent=`Показано ${rows.length} из ${METRICS.length}`;
}
function bindMetricFilters(){
  populateSelect('metric-state',METRICS.map(x=>x.state)); populateSelect('metric-unit',METRICS.map(x=>x.unit));
  const bindings=[['metric-search','query','input'],['metric-scope','scope','change'],['metric-state','state','change'],['metric-unit','unit','change'],['metric-sort','sort','change']];
  bindings.forEach(([id,key,event])=>$(id).addEventListener(event,e=>{state.metric[key]=e.target.value;renderMetrics();}));
  $('metric-reset').addEventListener('click',()=>{state.metric={query:'',scope:'',state:'',unit:'',sort:'id'};bindings.forEach(([id,key])=>$(id).value=state.metric[key]);renderMetrics();});
}

"""
