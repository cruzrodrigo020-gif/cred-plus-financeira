let MULTI_SALES=[];

const multiBaseRenderNav=multiRenderNav;
multiRenderNav=function(){
  const items=(MULTI_SUB&&!MULTI_SUB.active)
    ? [['subscription','💳 Assinatura']]
    : [['dashboard','📊 Dashboard'],['clients','👥 Clientes'],['sales','🛒 Vendas'],['loans','📄 Contratos'],['installments','📅 Parcelas detalhadas'],['goals','🎯 Metas e comissão'],['delinquency','⚠️ Inadimplência'],['closings','🧾 Fechamentos'],['cash','💰 Caixa'],['users','🧑‍💼 Usuários'],['reports','📁 Relatórios'],['profile','👤 Meu perfil']];
  M$('multiNav').innerHTML=items.map(([k,l])=>'<button class="'+(MULTI_PAGE===k?'active':'')+'" onclick="multiGo(\''+k+'\')">'+l+'</button>').join('')+'<div class="sep"></div><button onclick="multiLogout()">🚪 Sair</button>';
};

multiGo=async function(p){
  MULTI_PAGE=p;
  multiRenderNav();
  const titles={dashboard:'Dashboard Premium',clients:'Clientes',sales:'Vendas',loans:'Contratos',installments:'Parcelas detalhadas',goals:'Metas e comissão',delinquency:'Inadimplência',closings:'Fechamentos',cash:'Caixa',users:'Usuários',reports:'Relatórios',profile:'Meu perfil',subscription:'Assinatura'};
  M$('multiTitle').textContent=titles[p]||p;
  try{
    const fn=window['multiRender_'+p];
    if(typeof fn!=='function') throw new Error('Página indisponível.');
    await fn();
  }catch(e){mtoast(e.message)}
};

function multiSaleStatus(s){
  return s==='paid'
    ? '<span class="badge paid">Quitada</span>'
    : '<span class="badge active">Ativa</span>';
}

async function multiRender_sales(){
  if(!MULTI_CLIENTS.length){
    try{MULTI_CLIENTS=await mapi('/api/lender/clients')}catch{}
  }
  MULTI_SALES=await mapi('/api/lender/sales');
  const total=MULTI_SALES.reduce((s,x)=>s+Number(x.sale_value||0),0);
  const active=MULTI_SALES.filter(x=>x.status!=='paid').length;
  M$('multiContent').innerHTML=`
    <div class="kpis" style="grid-template-columns:repeat(3,minmax(160px,1fr))">
      <div class="kpi"><div class="lab">Vendas registradas</div><div class="val">${MULTI_SALES.length}</div></div>
      <div class="kpi"><div class="lab">Valor vendido</div><div class="val">${mmoney(total)}</div></div>
      <div class="kpi"><div class="lab">Vendas em aberto</div><div class="val">${active}</div></div>
    </div>
    <div class="card">
      <div class="toolbar">
        <div><h2>🛒 Vendas</h2><div class="muted">Venda produtos para clientes já cadastrados e parcele em até 12x.</div></div>
        <button class="btn btn-primary" onclick="multiSaleForm()">+ Nova venda</button>
      </div>
      <div class="table-wrap"><table>
        <tr><th>Cliente</th><th>Item</th><th>Venda</th><th>Valor</th><th>Parcelas</th><th>1º vencimento</th><th>Status</th><th>Ações</th></tr>
        ${MULTI_SALES.map(s=>`<tr>
          <td><b>${mesc(s.client)}</b></td>
          <td>${mesc(s.item_name)}</td>
          <td>${mesc(s.number)}</td>
          <td><b>${mmoney(s.sale_value)}</b></td>
          <td>${s.installments}x de ${mmoney(s.installment_value)}</td>
          <td>${mfmt(s.first_due)}</td>
          <td>${multiSaleStatus(s.status)}</td>
          <td><div class="actions">
            <button class="btn btn-soft btn-xs" onclick="multiSaleDetail(${s.id})">Abrir</button>
            <button class="btn btn-primary btn-xs" onclick="multiOpenSaleContract(${s.id})">Contrato</button>
            <button class="btn btn-ok btn-xs" onclick="multiSendSaleContract(${s.id})">WhatsApp</button>
          </div></td>
        </tr>`).join('')||'<tr><td colspan="8" class="empty">Nenhuma venda cadastrada.</td></tr>'}
      </table></div>
    </div>`;
}

function multiSaleForm(clientId=''){
  if(!MULTI_CLIENTS.length){
    mtoast('Cadastre um cliente primeiro');
    return multiGo('clients');
  }
  const tomorrow=(()=>{const d=new Date();d.setDate(d.getDate()+1);return d.toISOString().slice(0,10)})();
  const options=Array.from({length:12},(_,i)=>`<option value="${i+1}">${i+1}x</option>`).join('');
  multiOpen(`
    <div class="modal-head"><div><h2>Nova venda</h2><div class="muted">Cadastre o item e escolha de 1 a 12 parcelas.</div></div><button class="btn btn-soft" onclick="multiClose()">Fechar</button></div>
    <form id="multiSaleForm">
      <div class="form-section"><div class="form-grid">
        <div class="field wide"><label>Cliente *</label><select name="client_id" required>${MULTI_CLIENTS.map(c=>`<option value="${c.id}" ${String(c.id)===String(clientId)?'selected':''}>${mesc(c.name)}</option>`).join('')}</select></div>
        <div class="field wide"><label>Item vendido *</label><input name="item_name" required placeholder="Ex.: celular, geladeira, televisão"></div>
        <div class="field wide"><label>Descrição do item</label><textarea name="item_description" placeholder="Marca, modelo, cor, número de série ou outras informações"></textarea></div>
        <div class="field"><label>Valor total da venda *</label><input id="multiSaleValue" name="sale_value" type="number" min="0.01" step="0.01" required></div>
        <div class="field"><label>Parcelas *</label><select id="multiSaleInstallments" name="installments" required>${options}</select></div>
        <div class="field"><label>Primeiro vencimento *</label><input name="first_due" type="date" value="${tomorrow}" required></div>
        <div class="field"><label>Valor aproximado da parcela</label><input id="multiSalePreview" readonly value="R$ 0,00"></div>
      </div></div>
      <div class="foot"><button class="btn btn-primary">Registrar venda e gerar contrato</button></div>
    </form>`);
  const update=()=>{
    const value=Number(M$('multiSaleValue').value||0);
    const qty=Number(M$('multiSaleInstallments').value||1);
    M$('multiSalePreview').value=mmoney(qty?value/qty:0);
  };
  M$('multiSaleValue').addEventListener('input',update);
  M$('multiSaleInstallments').addEventListener('change',update);
  update();
  M$('multiSaleForm').onsubmit=async e=>{
    e.preventDefault();
    try{
      const d=await mapi('/api/lender/sales',{method:'POST',body:new FormData(e.currentTarget)});
      multiClose();
      mtoast('Venda registrada e contrato gerado');
      await multiSaleDetail(d.id);
    }catch(err){mtoast(err.message)}
  };
}

async function multiSaleDetail(id){
  const d=await mapi('/api/lender/sales/'+id);
  multiOpen(`
    <div class="modal-head">
      <div><h2>${mesc(d.item_name)}</h2><div class="muted">${mesc(d.client)} • ${mesc(d.number)}</div></div>
      <button class="btn btn-soft" onclick="multiClose()">Fechar</button>
    </div>
    <div class="mini-grid">
      <div class="mini"><div class="t">Valor da venda</div><div class="v">${mmoney(d.sale_value)}</div></div>
      <div class="mini"><div class="t">Parcelamento</div><div class="v">${d.installments}x</div></div>
      <div class="mini"><div class="t">Situação</div><div class="v">${d.status==='paid'?'Quitada':'Em aberto'}</div></div>
    </div>
    ${d.item_description?`<div class="card"><div class="muted">Descrição do item</div><div style="margin-top:6px">${mesc(d.item_description)}</div></div>`:''}
    <div class="card">
      <div class="toolbar"><h2>Parcelas da venda</h2><div class="actions">
        <button class="btn btn-soft" onclick="multiOpenSaleContract(${d.id})">📄 Abrir contrato</button>
        <button class="btn btn-primary" onclick="multiSendSaleContract(${d.id})">📲 Enviar contrato</button>
      </div></div>
      <div class="table-wrap"><table>
        <tr><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Pago</th><th>Status</th><th>Ação</th></tr>
        ${d.items.map(i=>`<tr>
          <td>${i.number}</td><td>${mfmt(i.due_date)}</td><td>${mmoney(i.amount)}</td><td>${mmoney(i.paid_amount)}</td>
          <td><span class="badge ${i.status==='paid'?'paid':(i.due_date<mtoday()?'overdue':'pending')}">${i.status==='paid'?'Pago':(i.due_date<mtoday()?'Atrasado':'Pendente')}</span></td>
          <td>${i.status==='paid'
            ? `<button class="btn btn-soft btn-xs" onclick="multiSaleUnpay(${d.id},${i.id})">Desfazer</button>`
            : `<button class="btn btn-ok btn-xs" onclick="multiSalePay(${d.id},${i.id})">Quitar</button>`}
          </td>
        </tr>`).join('')}
      </table></div>
    </div>`);
}

async function multiSalePay(saleId,installmentId){
  const f=new FormData();f.set('payment_date',mtoday());
  try{
    await mapi('/api/lender/sales/'+saleId+'/installments/'+installmentId+'/mark-paid',{method:'POST',body:f});
    mtoast('Parcela marcada como paga');
    multiSaleDetail(saleId);
  }catch(e){mtoast(e.message)}
}

async function multiSaleUnpay(saleId,installmentId){
  try{
    await mapi('/api/lender/sales/'+saleId+'/installments/'+installmentId+'/mark-unpaid',{method:'POST'});
    mtoast('Pagamento desfeito');
    multiSaleDetail(saleId);
  }catch(e){mtoast(e.message)}
}

async function multiOpenSaleContract(id){
  try{
    const d=await mapi('/api/lender/sales/'+id);
    if(!d.contract_path) throw new Error('Contrato indisponível.');
    window.open(d.contract_path,'_blank','noopener');
  }catch(e){mtoast(e.message)}
}

async function multiSendSaleContract(id){
  try{
    mtoast('Enviando contrato pelo WhatsApp...');
    const d=await mapi('/api/lender/sales/'+id+'/send-contract',{method:'POST'});
    mtoast('Contrato enviado ao cliente pelo WhatsApp');
  }catch(e){
    mtoast(e.message);
  }
}
