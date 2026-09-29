const _baseRenderContractsEdit = render_contracts;

render_contracts = async function(){
  const a = await api('/api/contracts');
  $('content').innerHTML = \`<div class="card"><div class="toolbar"><div><h2>Empréstimos e acordos</h2><div class="muted">Acordos podem ter de 1 a 10 parcelas com vencimento mensal.</div></div><div class="actions">\${U.role==='admin'?'<button class="btn btn-primary" onclick="contractForm(false)">+ Novo empréstimo</button><button class="btn btn-warn" onclick="contractForm(true)">+ Novo acordo</button>':''}<input class="search" placeholder="Buscar contrato ou cliente" oninput="filterRows('contractsBody',this.value)"></div></div><div class="table-wrap"><table><tr><th>Contrato</th><th>Tipo</th><th>Cliente</th><th>Principal</th><th>Total</th><th>Parcelas</th><th>1º vencimento</th><th>Status</th><th>Ação</th></tr><tbody id="contractsBody">\${a.map(k=>\`<tr><td><b>\${esc(k.number)}</b></td><td>\${k.periodicity==='monthly'?'<span class="badge pending">Acordo</span>':'<span class="badge active">Empréstimo</span>'}</td><td>\${esc(k.client)}</td><td>\${money(k.principal)}</td><td>\${money(k.total)}</td><td>\${k.installments}</td><td>\${fmt(k.first_due)}</td><td><span class="badge active">\${esc(k.status)}</span></td><td><div class="actions"><button class="btn btn-soft btn-xs" onclick="contractView(\${k.id})">Abrir</button>\${U.role==='admin'?\`<button class="btn btn-primary btn-xs" onclick="editContractForm(\${k.id})">Editar</button>\`:''}</div></td></tr>\`).join('')||'<tr><td colspan="9" class="empty">Nenhum empréstimo ou acordo.</td></tr>'}</tbody></table></div></div>\`;
};

async function editContractForm(id){
  if(U.role!=='admin') return;
  const [k,cs] = await Promise.all([api('/api/contracts/'+id), api('/api/clients')]);
  openModal(\`<div class="modal-head"><div><h2>Editar empréstimo</h2><div class="muted">\${esc(k.number)} • altere valor, juros, parcelas, cliente e vencimento.</div></div><button class="btn btn-soft" onclick="closeModal()">Fechar</button></div>
  <form id="editContractForm" onsubmit="saveContractEdit(event,\${id})">
    <div class="form-section"><div class="form-grid">
      <div class="field wide"><label>Cliente</label><select name="client_id">\${cs.map(x=>\`<option value="\${x.id}" \${String(x.id)===String(k.client_id)?'selected':''}>\${esc(x.name)}</option>\`).join('')}</select></div>
      <div class="field"><label>Valor principal</label><input id="editPrincipal" name="principal" type="number" min="0.01" step="0.01" value="\${Number(k.principal||0).toFixed(2)}" required oninput="editContractPreview()"></div>
      <div class="field"><label>Taxa de juros (%)</label><input id="editRate" name="rate" type="number" min="0" step="0.01" value="\${Number(k.rate||0).toFixed(2)}" required oninput="editContractPreview()"></div>
      <div class="field"><label>Número de parcelas</label><input id="editInstallments" name="installments" type="number" min="1" \${k.periodicity==='monthly'?'max="10"':''} value="\${Number(k.installments||1)}" required oninput="editContractPreview()" \${k.periodicity==='final'?'readonly':''}></div>
      <div class="field"><label>Primeiro vencimento</label><input name="first_due" type="date" value="\${esc(k.first_due||'')}" required></div>
      <div class="field wide"><label>Modalidade</label><input value="\${k.periodicity==='monthly'?'Acordo mensal':k.periodicity==='final'?'Pagamento final':'Empréstimo'}" disabled></div>
      <div class="field wide"><label>Prévia após edição</label><div id="editContractPreview" class="muted"></div></div>
    </div></div>
    <div class="hint-box"><b>Proteção do histórico:</b> contratos que já possuem pagamentos registrados não terão valores e quantidade de parcelas recalculados. Para esses casos, as datas individuais das parcelas podem continuar sendo alteradas pela opção <b>Data</b> ao abrir o contrato.</div>
    <div class="foot"><button type="button" class="btn btn-soft" onclick="closeModal()">Cancelar</button><button class="btn btn-primary">Salvar alterações</button></div>
  </form>\`);
  editContractPreview();
}

function editContractPreview(){
  const principal = Number($('editPrincipal')?.value||0);
  const rate = Number($('editRate')?.value||0);
  const n = Math.max(1, Number($('editInstallments')?.value||1));
  const total = principal * (1 + rate/100);
  const el = $('editContractPreview');
  if(el) el.innerHTML = \`Principal: <b>\${money(principal)}</b><br>Juros: <b>\${rate.toFixed(2)}%</b><br>Total: <b>\${money(total)}</b><br>Parcelas: <b>\${n}</b><br>Valor médio: <b>\${money(total/n)}</b>\`;
}

async function saveContractEdit(e,id){
  e.preventDefault();
  try{
    const r = await api('/api/contracts/'+id,{method:'PATCH',body:new FormData(e.target)});
    closeModal();
    toast('Empréstimo '+r.number+' atualizado com sucesso');
    await render_contracts();
  }catch(err){
    toast(err.message);
  }
}
