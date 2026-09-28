async function render_subscriptions(){
  if(U.role!=='admin')return;
  const rows=await api('/api/admin/subscriptions');
  const pending=rows.filter(x=>x.pending_id);
  $('content').innerHTML=`<div class="kpis" style="grid-template-columns:repeat(4,minmax(150px,1fr))">
    <div class="kpi"><div class="lab">Contas cadastradas</div><div class="val">${rows.length}</div></div>
    <div class="kpi"><div class="lab">Em teste grátis</div><div class="val">${rows.filter(x=>x.phase==='trial').length}</div></div>
    <div class="kpi"><div class="lab">Assinaturas ativas</div><div class="val">${rows.filter(x=>x.phase==='active').length}</div></div>
    <div class="kpi"><div class="lab">Aguardando aprovação</div><div class="val">${pending.length}</div></div>
  </div>
  <div class="card"><div class="toolbar"><div><h2>💳 Assinaturas do aplicativo</h2><div class="muted">7 dias grátis • R$ 24,99 por mês • aprovação manual via comprovante PIX.</div></div></div>
  <div class="table-wrap"><table><tr><th>Cliente</th><th>Login</th><th>Situação</th><th>Dias restantes</th><th>Pago até</th><th>Comprovante</th><th>Ação</th></tr><tbody>
  ${rows.map(x=>`<tr><td><b>${esc(x.name)}</b><br><span class="muted">${esc(x.whatsapp||'')}</span></td><td>${esc(x.email)}</td><td><span class="badge ${x.phase==='active'?'paid':x.phase==='trial'?'pending':'unpaid'}">${x.phase==='active'?'Ativa':x.phase==='trial'?'Teste grátis':'Expirada'}</span></td><td>${x.days_left}</td><td>${x.paid_until?fmt(x.paid_until):'-'}</td><td>${x.pending_id?'<button class="btn btn-soft btn-xs" onclick="openSubscriptionProof('+x.pending_id+')">Abrir comprovante</button>':'-'}</td><td>${x.pending_id?'<div class="actions"><button class="btn btn-ok btn-xs" onclick="approveSubscription('+x.pending_id+')">Aprovar +30 dias</button><button class="btn btn-soft btn-xs" onclick="rejectSubscription('+x.pending_id+')">Rejeitar</button></div>':'-'}</td></tr>`).join('')||'<tr><td colspan="7" class="empty">Nenhuma conta cadastrada.</td></tr>'}
  </tbody></table></div></div>`;
}
async function openSubscriptionProof(id){
  try{
    const r=await fetch('/api/admin/subscriptions/payments/'+id+'/proof',{headers:{Authorization:'Bearer '+T}});
    if(!r.ok)return toast('Não foi possível abrir o comprovante');
    const b=await r.blob();window.open(URL.createObjectURL(b),'_blank');
  }catch(e){toast(e.message)}
}
async function approveSubscription(id){
  try{await api('/api/admin/subscriptions/payments/'+id+'/approve',{method:'POST'});toast('Pagamento aprovado e acesso liberado por 30 dias');render_subscriptions()}catch(e){toast(e.message)}
}
async function rejectSubscription(id){
  try{await api('/api/admin/subscriptions/payments/'+id+'/reject',{method:'POST'});toast('Comprovante rejeitado');render_subscriptions()}catch(e){toast(e.message)}
}
