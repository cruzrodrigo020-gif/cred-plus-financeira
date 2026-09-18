function installmentSmartBadge(i){
  if(i.status==='paid')return '<span class="badge paid">Pago</span>';
  if(i.status==='partial')return '<span class="badge pending">Parcial</span>';
  if(i.status==='renewed')return '<span class="badge active">Renovado</span>';
  const overdue=i.due_date&&String(i.due_date).slice(0,10)<new Date().toISOString().slice(0,10);
  if(overdue)return '<span class="badge overdue">Atrasado</span>';
  if(i.status==='unpaid')return '<span class="badge unpaid">Nao pago</span>';
  return '<span class="badge pending">Pendente</span>';
}

render_installments=async function(){
  const a=await api('/api/installments/extended');
  const renewalShown=new Set();
  $('content').innerHTML=`<div class="card"><div class="toolbar"><div><h2>Parcelas detalhadas</h2><div class="muted">Registre pagamento total, parcial ou renove o emprestimo quando o cliente pagar somente os juros.</div></div><input class="search" placeholder="Buscar cliente, contrato ou parcela" oninput="filterRows('instBody',this.value)"></div><div class="table-wrap"><table><tr><th>Cliente</th><th>Contrato</th><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Pago</th><th>Saldo</th><th>Status</th><th>Acoes</th></tr><tbody id="instBody">${a.map(i=>{
    const showRenew=U.role==='admin'&&!renewalShown.has(i.contract_id);
    if(showRenew)renewalShown.add(i.contract_id);
    const clientSafe=esc(i.client).replace(/'/g,'&#39;');
    const partialBtn=U.role==='admin'?`<button class="btn btn-primary btn-xs" onclick="partialPaymentForm(${i.id},'${clientSafe}',${i.remaining})">Parcial</button>`:'';
    const renewBtn=showRenew?`<button class="btn btn-warn btn-xs" onclick="renewInterestForm(${i.contract_id})">Renovar juros</button>`:'';
    return `<tr><td>${esc(i.client)}</td><td>${esc(i.contract)}</td><td><b>${String(i.number).padStart(2,'0')}</b></td><td>${fmt(i.due_date)}</td><td>${money(i.amount)}</td><td>${money(i.paid_amount)}</td><td><b>${money(i.remaining)}</b></td><td>${installmentSmartBadge(i)}</td><td><div class="actions"><button class="btn btn-ok btn-xs" onclick="markPaid(${i.id})">Quitar</button>${partialBtn}${renewBtn}<button class="btn btn-bad btn-xs" onclick="markUnpaid(${i.id})">Nao pago</button></div></td></tr>`;
  }).join('')||'<tr><td colspan="9" class="empty">Nenhuma parcela ativa.</td></tr>'}</tbody></table></div></div>`;
};

function partialPaymentForm(id,client,remaining){
  if(U.role!=='admin')return;
  openModal(`<div class="modal-head"><div><h2>Pagamento parcial</h2><div class="muted">${esc(client)} â¢ Saldo da parcela: <b>${money(remaining)}</b></div></div><button class="btn btn-soft" onclick="closeModal()">Fechar</button></div><form onsubmit="savePartialPayment(event,${id})"><div class="form-section"><div class="form-grid"><div class="field"><label>Valor recebido</label><input name="amount" type="number" min="0.01" max="${Number(remaining).toFixed(2)}" step="0.01" required autofocus></div><div class="field"><label>Data do pagamento</label><input name="payment_date" type="date" value="${new Date().toISOString().slice(0,10)}"></div><div class="field"><label>Forma de pagamento</label><select name="method"><option>PIX</option><option>Dinheiro</option><option>Transferencia</option><option>Outro</option></select></div><div class="field"><label>Observacao</label><input name="note" value="Pagamento parcial"></div></div></div><div class="foot"><button type="button" class="btn btn-soft" onclick="closeModal()">Cancelar</button><button class="btn btn-primary">Registrar parcial</button></div></form>`);
}

async function savePartialPayment(e,id){
  e.preventDefault();
  const btn=e.submitter;
  if(btn)btn.disabled=true;
  try{
    const r=await api(`/api/installments/${id}/partial-payment`,{method:'POST',body:new FormData(e.target)});
    closeModal();
    toast(`Pagamento parcial registrado. Saldo: ${money(r.remaining)}`);
    if(r.payment_id)downloadReceipt(r.payment_id);
    await render_installments();
  }catch(err){
    toast(err.message);
    if(btn)btn.disabled=false;
  }
}

async function renewInterestForm(contractId){
  if(U.role!=='admin')return;
  try{
    const x=await api(`/api/contracts/${contractId}/renewal-preview`);
    openModal(`<div class="modal-head"><div><h2>Renovar pagando somente os juros</h2><div class="muted">${esc(x.contract)}</div></div><button class="btn btn-soft" onclick="closeModal()">Fechar</button></div><div class="mini-grid"><div class="mini"><div class="t">Principal mantido</div><div class="v">${money(x.principal)}</div></div><div class="mini"><div class="t">Juros do ciclo</div><div class="v">${money(x.interest_due)}</div></div><div class="mini"><div class="t">Pagar agora</div><div class="v">${money(x.interest_to_pay_now)}</div></div></div><div class="form-section"><div class="muted">Na renovacao, o cliente paga somente os juros do ciclo atual. O principal de <b>${money(x.principal)}</b> permanece e um novo contrato e gerado. Nao ha nova saida de principal no caixa.</div></div><form onsubmit="saveInterestRenewal(event,${contractId})"><div class="form-section"><div class="form-grid"><div class="field"><label>Novo primeiro vencimento</label><input name="first_due" type="date" value="${x.recommended_first_due}" required></div><div class="field"><label>Data do pagamento dos juros</label><input name="payment_date" type="date" value="${new Date().toISOString().slice(0,10)}"></div><div class="field wide"><label>Forma de pagamento</label><select name="method"><option>PIX</option><option>Dinheiro</option><option>Transferencia</option><option>Outro</option></select></div></div></div><div class="foot"><button type="button" class="btn btn-soft" onclick="closeModal()">Cancelar</button><button class="btn btn-warn">Confirmar renovacao</button></div></form>`);
  }catch(err){toast(err.message)}
}

async function saveInterestRenewal(e,contractId){
  e.preventDefault();
  const btn=e.submitter;
  if(btn)btn.disabled=true;
  try{
    const r=await api(`/api/contracts/${contractId}/renew-interest`,{method:'POST',body:new FormData(e.target)});
    closeModal();
    toast(`Renovado: ${r.new_contract} â¢ Juros pagos ${money(r.interest_paid)}`);
    if(r.payment_id)downloadReceipt(r.payment_id);
    await render_installments();
  }catch(err){
    toast(err.message);
    if(btn)btn.disabled=false;
  }
}
