function installmentPriority(i,today){
  const due=String(i.due_date||'').slice(0,10);
  const paid=i.status==='paid'||Number(i.remaining||0)<=0.005;
  if(paid)return 3;
  if(due>=today)return 0;
  return 1;
}

function installmentDaysLabel(i,today){
  const due=String(i.due_date||'').slice(0,10);
  if(!due)return '-';
  const base=new Date(today+'T00:00:00');
  const d=new Date(due+'T00:00:00');
  const days=Math.round((d-base)/86400000);
  if(days===0)return '<span class="badge pending">Vence hoje</span>';
  if(days===1)return '<span class="badge active">Vence amanhã</span>';
  if(days>1)return `<span class="badge active">Vence em ${days} dias</span>`;
  return `<span class="badge overdue">${Math.abs(days)} dia(s) atrasada</span>`;
}

render_installments=async function(){
  const raw=await api('/api/installments/extended');
  const today=new Date().toISOString().slice(0,10);
  const in7=new Date();in7.setDate(in7.getDate()+7);const limit7=in7.toISOString().slice(0,10);
  const a=[...raw].sort((x,y)=>{
    const px=installmentPriority(x,today),py=installmentPriority(y,today);
    if(px!==py)return px-py;
    const dx=String(x.due_date||'9999-12-31'),dy=String(y.due_date||'9999-12-31');
    if(px===1)return dy.localeCompare(dx);
    return dx.localeCompare(dy);
  });
  const active=a.filter(i=>i.status!=='paid'&&Number(i.remaining||0)>0.005);
  const dueToday=active.filter(i=>String(i.due_date).slice(0,10)===today);
  const next7=active.filter(i=>{const d=String(i.due_date).slice(0,10);return d>today&&d<=limit7});
  const overdue=active.filter(i=>String(i.due_date).slice(0,10)<today);
  const dueTodayValue=dueToday.reduce((s,i)=>s+Number(i.remaining||0),0);
  const next7Value=next7.reduce((s,i)=>s+Number(i.remaining||0),0);
  const overdueValue=overdue.reduce((s,i)=>s+Number(i.remaining||0),0);
  const renewalShown=new Set();
  $('content').innerHTML=`<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
    <div class="kpi"><div class="lab">Vencem hoje</div><div class="val">${dueToday.length}</div><div class="muted">${money(dueTodayValue)}</div></div>
    <div class="kpi"><div class="lab">Próximos 7 dias</div><div class="val">${next7.length}</div><div class="muted">${money(next7Value)}</div></div>
    <div class="kpi"><div class="lab">Vencidas</div><div class="val">${overdue.length}</div><div class="muted">${money(overdueValue)}</div></div>
    <div class="kpi"><div class="lab">Parcelas ativas</div><div class="val">${active.length}</div></div>
  </div>
  <div class="card"><div class="toolbar"><div><h2>Parcelas detalhadas</h2><div class="muted">As parcelas a vencer aparecem primeiro, da data mais próxima para a mais distante. Depois vêm as vencidas e, por último, as quitadas.</div></div><input class="search" placeholder="Buscar cliente, contrato ou parcela" oninput="filterRows('instBody',this.value)"></div>
  <div class="table-wrap"><table><tr><th>Prioridade</th><th>Cliente</th><th>Contrato</th><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Pago</th><th>Saldo</th><th>Status</th><th>Ações</th></tr><tbody id="instBody">${a.map(i=>{
    const showRenew=U.role==='admin'&&!renewalShown.has(i.contract_id)&&i.status!=='paid'&&Number(i.remaining||0)>0.005;
    if(showRenew)renewalShown.add(i.contract_id);
    const clientSafe=esc(i.client).replace(/'/g,'&#39;');
    const partialBtn=U.role==='admin'&&i.status!=='paid'?`<button class="btn btn-primary btn-xs" onclick="partialPaymentForm(${i.id},'${clientSafe}',${i.remaining})">Parcial</button>`:'';
    const renewBtn=showRenew?`<button class="btn btn-warn btn-xs" onclick="renewInterestForm(${i.contract_id})">Renovar juros</button>`:'';
    const payBtns=i.status==='paid'||Number(i.remaining||0)<=0.005?'':`<button class="btn btn-ok btn-xs" onclick="markPaid(${i.id})">Quitar</button>${partialBtn}${renewBtn}<button class="btn btn-bad btn-xs" onclick="markUnpaid(${i.id})">Não pago</button>`;
    return `<tr><td>${installmentDaysLabel(i,today)}</td><td>${esc(i.client)}</td><td>${esc(i.contract)}</td><td><b>${String(i.number).padStart(2,'0')}</b></td><td>${fmt(i.due_date)}</td><td>${money(i.amount)}</td><td>${money(i.paid_amount)}</td><td><b>${money(i.remaining)}</b></td><td>${installmentSmartBadge(i)}</td><td><div class="actions">${payBtns}</div></td></tr>`;
  }).join('')||'<tr><td colspan="10" class="empty">Nenhuma parcela ativa.</td></tr>'}</tbody></table></div></div>`;
};
