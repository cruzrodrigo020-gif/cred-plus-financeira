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
            <button class="btn btn-soft btn-xs" onclick="saleEdit(${s.id})">Editar</button>
            <button class="btn btn-soft btn-xs" onclick="saleDelete(${s.id})">Excluir</button>
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


async function saleEdit(id){
  try{
    const d=await api('/api/sales/'+id);
    const clients=window.ADMIN_SALE_CLIENTS||[];
    const paid=d.items.some(i=>i.status==='paid'||Number(i.paid_amount||0)>0);
    const options=Array.from({length:12},(_,i)=>'<option value="'+(i+1)+'" '+(d.installments===i+1?'selected':'')+'>'+(i+1)+'x</option>').join('');
    openModal(`
      <div class="modal-head"><div><h2>Editar contrato</h2><div class="muted">${esc(d.number)}</div></div><button class="btn btn-soft" onclick="closeModal()">Fechar</button></div>
      ${paid?'<p class="muted">Este contrato possui parcelas pagas. Apenas o nome e a descrição do item podem ser alterados.</p>':''}
      <form id="saleEditForm">
        <div class="form-section"><div class="form-grid">
          <div class="field wide"><label>Cliente</label><select name="client_id" ${paid?'disabled':''} required>${clients.map(x=>'<option value="'+x.id+'" '+(x.id===d.client_id?'selected':'')+'>'+esc(x.name)+'</option>').join('')}</select></div>
          <div class="field wide"><label>Item vendido</label><input name="item_name" required maxlength="220" value="${esc(d.item_name)}"></div>
          <div class="field wide"><label>Descrição</label><textarea name="item_description">${esc(d.item_description||'')}</textarea></div>
          <div class="field"><label>Valor da venda</label><input name="sale_value" type="number" step="0.01" min="0.01" value="${d.sale_value}" ${paid?'disabled':''} required></div>
          <div class="field"><label>Parcelas</label><select name="installments" ${paid?'disabled':''} required>${options}</select></div>
          <div class="field"><label>Primeiro vencimento</label><input name="first_due" type="date" value="${d.first_due}" ${paid?'disabled':''} required></div>
        </div></div>
        <div class="foot"><button type="button" class="btn btn-soft" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" type="submit">Salvar alterações</button></div>
      </form>`);
    const form=$('saleEditForm');
    form.onsubmit=async event=>{
      event.preventDefault();
      const data=new FormData(form);
      if(paid){
        data.set('client_id',String(d.client_id));
        data.set('sale_value',String(d.sale_value));
        data.set('installments',String(d.installments));
        data.set('first_due',d.first_due);
      }
      try{
        await api('/api/sales/'+id,{method:'PUT',body:data});
        closeModal();toast('Contrato atualizado');await render_sales();
      }catch(error){toast(error.message)}
    };
  }catch(error){toast(error.message)}
}

async function saleDelete(id){
  try{
    const d=await api('/api/sales/'+id);
    if(d.items.some(i=>i.status==='paid'||Number(i.paid_amount||0)>0)){
      toast('Não é possível excluir contrato com parcelas pagas');return;
    }
    if(!confirm('Excluir definitivamente o contrato '+d.number+' de '+d.client+'? Esta ação não pode ser desfeita.'))return;
    await api('/api/sales/'+id,{method:'DELETE'});
    closeModal();toast('Contrato excluído');await render_sales();
  }catch(error){toast(error.message)}
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
    const sale=await api('/api/sales/'+id);
    const number=String(sale.client_whatsapp||'').replace(/[^0-9]/g,'');
    const phone=number.length===10||number.length===11?'55'+number:number;
    if(phone.length<12){toast('Cadastre o WhatsApp do cliente com DDD');return;}
    const pdf=new URL(sale.contract_path,window.location.origin).href;
    const msg='Olá, '+sale.client+'. Segue o contrato de compra e venda de '+sale.item_name+', no valor de '+money(sale.sale_value)+': '+pdf;
    const url='https://wa.me/'+phone+'?text='+encodeURIComponent(msg);
    window.open(url,'_blank');
    toast('Conversa aberta. Confirme o envio no WhatsApp.');
  }catch(e){toast(e.message)}
}


/* Navegação final: este arquivo é carregado por último para impedir que módulos antigos removam Vendas. */
renderNav=function(){
  const items=[
    ['dashboard','📊 Dashboard'],
    ['clients','👥 Clientes'],
    ['sales','🛒 Vendas'],
    ['projection','📈 Projeção do mês'],
    ['contracts','📄 Contratos'],
    ['installments','📅 Parcelas detalhadas'],
    ['collectors','🧭 Cobradores'],
    ['goals','🎯 Metas e comissão'],
    ['route','🗺️ Agenda / Rota'],
    ['analytics','📈 Inadimplência'],
    ['closings','🧾 Fechamentos'],
    ['cash','💰 Caixa'],
    ['reports','📁 Relatórios PDF'],
    ['appusers','👤 Usuários do App'],
    ['users','🧑‍💼 Usuários'],
    ['chat','💬 Chat'],
    ['security','🔐 Segurança e Senha']
  ].filter(x=>!(U?.role!=='admin'&&['sales','projection','collectors','cash','reports','appusers','users','security'].includes(x[0])));
  $('nav').innerHTML=items.map(([k,l])=>`<button class="${PAGE===k?'active':''}" onclick="go('${k}')">${l}${k==='chat'?'<span id="adminChatNavBadge"></span>':''}</button>`).join('')+`<div class="sep"></div><button onclick="logout()">🚪 Sair</button>`;
  if(typeof refreshAdminChatBadge==='function') refreshAdminChatBadge();
};

go=async function(p){
  PAGE=p;
  renderNav();
  const titles={
    dashboard:'Dashboard Premium',
    clients:'Clientes',
    sales:'Vendas',
    projection:'Projeção até o fim do mês',
    contracts:'Contratos',
    installments:'Parcelas detalhadas',
    collectors:'Central de Cobradores',
    goals:'Metas e Comissão',
    route:'Agenda e Rota de Cobrança',
    analytics:'Painel de Inadimplência',
    closings:'Fechamentos',
    cash:'Caixa',
    reports:'Relatórios PDF',
    appusers:'Usuários do App',
    users:'Usuários',
    chat:'Chat interno',
    security:'Segurança e Senha'
  };
  $('title').textContent=titles[p]||p;
  try{
    const fn=window['render_'+p];
    if(typeof fn!=='function') throw new Error('Tela indisponível.');
    await fn();
  }catch(e){toast(e.message)}
};
