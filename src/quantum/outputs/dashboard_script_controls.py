from __future__ import annotations

DASHBOARD_JS_CONTROLS = r"""
function qualityCard(label,value){ const card=el('article','status-card'); append(card,el('div','status-label',label),append(el('div','status-value'),badge(value))); return card; }
function renderQuality(){
  const grid=$('quality-grid'); clear(grid);
  const entries=[['Admission',Q.admission_state],['Storage zone',Q.storage_zone_state],['Source bridge',Q.source_bridge_status],['Finance request',Q.finance_request_state],['Raw rows',Q.raw_rows_in_report===false?'FORBIDDEN':'CHECK'],['Blocked metrics',(Q.blocked_metrics||[]).length],['Reason codes',(Q.reason_codes||[]).length],['Inspection diagnostics',(Q.inspection_diagnostics||[]).length]];
  entries.forEach(([l,v])=>grid.appendChild(qualityCard(l,v)));
  const rec=$('reconciliation-panel'); clear(rec); const stateValue=B.reconciliation?.state||'NOT_AVAILABLE'; append(rec,badge(stateValue));
  const differences=B.reconciliation?.differences||[]; if(differences.length){const list=el('ul','list-clean');differences.forEach(x=>list.appendChild(el('li','',typeof x==='string'?x:JSON.stringify(x))));rec.appendChild(list);} else rec.appendChild(el('p','', 'Различия не зарегистрированы.'));
  const limits=$('limitations-list'); clear(limits); (B.limitations||[]).forEach(x=>limits.appendChild(el('li','',x))); if(!(B.limitations||[]).length) limits.appendChild(el('li','', 'Ограничения не зарегистрированы.'));
  const hashes=[['Bundle SHA-256',B.bundle_hash],['Source SHA-256',B.source_sha256],['Calculation result SHA-256',P.calculation?.result_hash],['Recommendation bundle SHA-256',P.recommendations?.bundle_hash],['Canonical rows SHA-256',P.source?.canonical_rows_sha256],['Canonical ledger SHA-256',P.source?.canonical_ledger_sha256]];
  const hashGrid=$('hash-grid'); clear(hashGrid); hashes.forEach(([label,value])=>{ const card=el('article','hash-card'); const button=el('button','button button-quiet button-small','Копировать'); button.type='button'; button.addEventListener('click',()=>copyText(value)); append(card,el('div','hash-label',label),el('div','hash-value',value||'—'),append(el('div','hash-actions'),button)); hashGrid.appendChild(card); });
  const params=$('parameters-list'); clear(params); const flat=[['Calculation mode',B.parameters?.calculation_mode],['Scenario',B.parameters?.scenario_id],['Calculated at',B.parameters?.calculated_at],['Publication state',B.parameters?.publication_state],['Profile reference',B.parameters?.calculation_profile_ref],['Rounding policy',B.parameters?.rounding_policy_ref],['Runtime profile',P.runtime?.runtime_profile],['Runner version',P.runtime?.runner_version],['Storage encryption required',P.runtime?.storage_encryption_required],['Marketplace writes',P.runtime?.marketplace_write_enabled]];
  flat.forEach(([label,value])=>{params.appendChild(el('dt','',label));params.appendChild(el('dd','',typeof value==='object'&&value!==null?JSON.stringify(value):value));});
}
async function copyText(value){
  const content=text(value); try{ if(navigator.clipboard&&navigator.clipboard.writeText){await navigator.clipboard.writeText(content);} else {const area=document.createElement('textarea');area.value=content;area.className='screen-reader';document.body.appendChild(area);area.select();document.execCommand('copy');area.remove();} toast('Скопировано'); }catch(_){ toast('Копирование недоступно'); }
}

function drawerSection(title,content,className=''){
  const section=el('section','drawer-section'); section.appendChild(el('h3','',title));
  if(Array.isArray(content)){const list=el('ul','list-clean');content.forEach(x=>list.appendChild(el('li','',x)));section.appendChild(list);}
  else section.appendChild(el('div',className,content)); return section;
}
function openDrawer(title,sections,trigger){
  state.lastFocus=trigger||document.activeElement; $('drawer-title').textContent=title; const body=$('drawer-body'); clear(body); sections.forEach(x=>body.appendChild(x));
  document.body.classList.add('drawer-open'); $('detail-drawer').setAttribute('aria-hidden','false'); $('drawer-overlay').setAttribute('aria-hidden','false'); $('drawer-close').focus();
}
function closeDrawer(){ document.body.classList.remove('drawer-open'); $('detail-drawer').setAttribute('aria-hidden','true'); $('drawer-overlay').setAttribute('aria-hidden','true'); if(state.lastFocus&&state.lastFocus.focus) state.lastFocus.focus(); }
$('drawer-close').addEventListener('click',closeDrawer); $('drawer-overlay').addEventListener('click',closeDrawer); document.addEventListener('keydown',event=>{
  if(!document.body.classList.contains('drawer-open')) return;
  if(event.key==='Escape'){ closeDrawer(); return; }
  if(event.key==='Tab'){
    const focusable=[...$('detail-drawer').querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter(node=>!node.disabled);
    if(!focusable.length) return;
    const first=focusable[0],last=focusable[focusable.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  }
});
function openRecommendation(item,trigger){
  const sections=[drawerSection('Действие',actionLabel(item)),drawerSection('Причина',reasonLabel(item)),drawerSection('Эффект',[`Текущий: ${effectText(item.current_effect)}`,`Прогноз min: ${effectText(item.forecast_effect_min||item.forecast_effect)}`,`Прогноз max: ${effectText(item.forecast_effect_max||item.forecast_effect)}`]),drawerSection('Evidence',item.evidence_refs||[]),drawerSection('Ограничения',item.limitations||[]),drawerSection('Технический контракт',JSON.stringify({recommendation_id:item.recommendation_id,action_code:item.action_code,severity:item.severity,priority:item.priority_dimension,category:item.category,confidence:item.confidence_level||item.confidence?.state},null,2),'drawer-code')];
  openDrawer(actionLabel(item),sections,trigger);
}
function openMetric(item,trigger){
  const sections=[drawerSection('Значение',format(item.value,item.unit,item.currency)),drawerSection('Состояние',item.state),drawerSection('Причина',item.reason_code||'—'),drawerSection('Accounting view',item.accounting_view||'—'),drawerSection('Expense boundary',Array.isArray(item.expense_boundary)?item.expense_boundary:[]),drawerSection('Источники',Array.isArray(item.source_ids)?item.source_ids:[]),drawerSection('Полный контракт',JSON.stringify(item,null,2),'drawer-code')];
  openDrawer(item.id,sections,trigger);
}

function initialize(){
  $('nav-rec-count').textContent=String(RECOMMENDATIONS.length); $('nav-metric-count').textContent=String(METRICS.length);
  bindRecFilters(); bindMetricFilters(); renderOverview(); renderRecommendations(); renderMetrics(); renderQuality();
}
initialize();
"""
