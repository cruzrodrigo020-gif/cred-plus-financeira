let ADMIN_SALES=[];

async function render_sales(){
  if(U?.role!=='admin'){
    $('content').innerHTML='<div class="card"><div class="empty">Acesso restrito ao administrador.</div></div>';
    return;
  }
  const [sales,clients]=await Promise.all([api('/api/sales'),api('/api/clients')]);
  ADMIN_SALES=sales;
  window.ADMIN_SALE_CLIENTS=clients;
  const total=sales.reduce((sum,x)=>sum+Number(x.sale_value||0),0);
  const open=sales.filter(x=>x.status!=='paid').length;
  $('content').innerHTML=`
    <div class="kpis">
      <div class="kpi"><div class="lab">Vendas</div><div class="val">${sales.length}</div></div>
      <div class="kpi"><div class="lab">Valor vendido</div><div class="val">${money(total)}</div></div>
      <div class="kpi"><div class="lab">Em aberto</div><div class="val">${open}</div></div>
    </div>
    <div class="card">
      <div class="toolbar">
        <div><h2>🛒 Vendas</h2><div class="muted">Use clientes já cadastrados e parcele em até 12x.</div></div>
        <div class="actions"><button class="btn btn-primary" onclick="saleForm()">+ Nova venda</button><input class="search" placeholder="Buscar venda" oninput="filterRows('salesBody',this.value)"></div>
      </div>
      <div class="table-wrap"><table>
        <tr><th>Cliente</th><th>Item</th><th>Venda</th><th>Valor</th><th>Parcelas</th><th>1º vencimento</th><th>Status</th><th>Ações</th></tr>
        <tbody id="salesBody">
        ${sales.map(s=>`<tr>
          <td><b>${esc(s.client)}</b></td>
          <td>${esc(s.item_name)}</td>
          <td>${esc(s.number)}</td>
          <td><b>${money(s.sale_value)}</b></td>
          <td>${s.installments}x de ${money(s.installment_value)}</td>
          <td>${fmt(s.first_due)}</td>
          <td><span class="badge ${s.status==='paid'?'paid':'active'}">${s.status==='paid'?'Quitada':'Ativa'}</span></td>
          <td><div class="actions">
            <button class="btn btn-soft btn-xs" onclick="saleView(${s.id})">Abrir</button>
            <button class="btn btn-primary btn-xs" onclick="saleContract(${s.id})">Contrato</button>
            <button class="btn btn-ok btn-xs" onclick="saleSendContract(${s.id})">WhatsApp</button>
          </div></td>
        </tr>`).join('')||'<tr><td colspan="8" class="empty">Nenhuma venda cadastrada.</td></tr>'}
        </tbody>
      </table></div>
    </div>`;
}

function saleForm(clientId=''){
  const clients=window.ADMIN_SALE_CLIENTS||[];
  if(!clients.length){
    toast('Cadastre um cliente primeiro');
    return go('clients');
  }
  const next=(()=>{const d=new Date();d.setMonth(d.getMonth()+1);return d.toISOString().slice(0,10)})();
  const parts=Array.from({length:12},(_,i)=>`<option value="${i+1}">${i+1}x</option>`).join('');
  openModal(`
    <div class="modal-head"><div><h2>Nova venda</h2><div class="muted">Cadastre o item, o valor e o parcelamento.</div></div><button class="btn btn-soft" onclick="closeModal()">Fechar</button></div>
    <form id="saleFormEl">
      <div class="form-section"><div class="form-grid">
        <div class="field wide"><label>Cliente *</label><select name="client_id" required>${clients.map(c=>`<option value="${c.id}" ${String(c.id)===String(clientId)?'selected':''}>${esc(c.name)}</option>`).join('')}</select></div>
        <div class="field wide"><label>Item vendido *</label><input name="item_name" required placeholder="Ex.: celular, televisão, geladeira"></div>
        <div class="field wide"><label>Descrição do item</label><textarea name="item_description" placeholder="Marca, modelo, cor, número de série, estado do produto..."></textarea></div>
        <div class="field"><label>Valor da venda *</label><input id="saleValue" name="sale_value" type="number" min="0.01" step="0.01" required></div>
        <div class="field"><label>Parcelas *</label><select id="saleQty" name="installments" required>${parts}</select></div>
        <div class="field"><label>Primeiro vencimento *</label><input name="first_due" type="date" value="${next}" required></div>
        <div class="field"><label>Valor aproximado da parcela</label><input id="salePreview" readonly value="R$ 0,00"></div>
      </div></div>
      <div class="foot"><button type="button" class="btn btn-soft" onclick="closeModal()">Cancelar</button><button class="btn btn-primary">Registrar venda</button></div>
    </form>`);
  const update=()=>{
    const value=Number($('saleValue').value||0), qty=Number($('saleQty').value||1);
    $('salePreview').value=money(qty?value/qty:0);
  };
  $('saleValue').addEventListener('input',update);
  $('saleQty').addEventListener('change',update);
  update();
  $('saleFormEl').onsubmit=async e=>{
    e.preventDefault();
    try{
      const created=await api('/api/sales',{method:'POST',body:new FormData(e.currentTarget)});
      closeModal();
      toast('Venda registrada e contrato gerado');
      await render_sales();
      await saleView(created.id);
    }catch(err){toast(err.message)}
  };
}

async function saleView(id){
  const d=await api('/api/sales/'+id);
  openModal(`
    <div class="modal-head">
      <div><h2>${esc(d.item_name)}</h2><div class="muted">${esc(d.client)} • ${esc(d.number)}</div></div>
      <button class="btn btn-soft" onclick="closeModal()">Fechar</button>
    </div>
    <div class="mini-grid">
      <div class="mini"><div class="t">Valor</div><div class="v">${money(d.sale_value)}</div></div>
      <div class="mini"><div class="t">Parcelamento</div><div class="v">${d.installments}x</div></div>
      <div class="mini"><div class="t">Status</div><div class="v">${d.status==='paid'?'Quitada':'Em aberto'}</div></div>
    </div>
    ${d.item_description?`<div class="form-section"><div class="form-title">Descrição do item</div>${esc(d.item_description)}</div>`:''}
    <div class="card">
      <div class="toolbar"><h2>Parcelas</h2><div class="actions">
        <button class="btn btn-soft" onclick="saleContract(${d.id})">📄 Abrir contrato</button>
        <button class="btn btn-primary" onclick="saleSendContract(${d.id})">📲 Enviar contrato</button>
      </div></div>
      <div class="table-wrap"><table>
        <tr><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Pago</th><th>Status</th><th>Ação</th></tr>
        ${d.items.map(i=>`<tr>
          <td>${i.number}</td><td>${fmt(i.due_date)}</td><td>${money(i.amount)}</td><td>${money(i.paid_amount)}</td>
          <td>${badge(i.status,i.due_date)}</td>
          <td>${i.status==='paid'
            ? `<button class="btn btn-soft btn-xs" onclick="saleUnpay(${d.id},${i.id})">Desfazer</button>`
            : `<button class="btn btn-ok btn-xs" onclick="salePay(${d.id},${i.id})">Quitar</button>`}
          </td>
        </tr>`).join('')}
      </table></div>
    </div>`);
}

async function salePay(saleId,itemId){
  const f=new FormData();f.set('payment_date',new Date().toISOString().slice(0,10));
  try{
    await api('/api/sales/'+saleId+'/installments/'+itemId+'/mark-paid',{method:'POST',body:f});
    toast('Parcela marcada como paga');
    await saleView(saleId);
  }catch(e){toast(e.message)}
}

async function saleUnpay(saleId,itemId){
  try{
    await api('/api/sales/'+saleId+'/installments/'+itemId+'/mark-unpaid',{method:'POST'});
    toast('Pagamento desfeito');
    await saleView(saleId);
  }catch(e){toast(e.message)}
}

async function saleContract(id){
  try{
    const d=await api('/api/sales/'+id);
    window.open(d.contract_path,'_blank','noopener');
  }catch(e){toast(e.message)}
}

async function saleSendContract(id){
  try{
    toast('Enviando contrato pelo WhatsApp...');
    await api('/api/sales/'+id+'/send-contract',{method:'POST'});
    toast('Contrato enviado pelo WhatsApp');
  }catch(e){toast(e.message)}
}
