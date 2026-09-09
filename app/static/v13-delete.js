const _renderClientsBeforeDelete = render_clients;
render_clients = async function(){
  await _renderClientsBeforeDelete();
  if(U?.role !== 'admin') return;
  const clients = await api('/api/clients');
  const rows = Array.from(document.querySelectorAll('#clientsBody tr'));
  clients.forEach((c, idx) => {
    const row = rows[idx];
    if(!row) return;
    const box = row.querySelector('td:last-child .actions');
    if(box && !box.querySelector('.delete-client-btn')){
      box.insertAdjacentHTML('beforeend', `<button class="btn btn-bad btn-xs delete-client-btn" onclick="deleteClient(${c.id},'${esc(c.name).replace(/'/g,'&#39;')}')">Excluir</button>`);
    }
  });
};

const _renderContractsBeforeDelete = render_contracts;
render_contracts = async function(){
  await _renderContractsBeforeDelete();
  if(U?.role !== 'admin') return;
  const contracts = await api('/api/contracts');
  const rows = Array.from(document.querySelectorAll('#contractsBody tr'));
  contracts.forEach((c, idx) => {
    const row = rows[idx];
    if(!row) return;
    const box = row.querySelector('td:last-child');
    if(box && !box.querySelector('.delete-contract-btn')){
      box.insertAdjacentHTML('beforeend', ` <button class="btn btn-bad btn-xs delete-contract-btn" onclick="deleteContract(${c.id},'${esc(c.number)}')">Excluir</button>`);
    }
  });
};

const _clientViewBeforeDelete = clientView;
clientView = async function(id){
  await _clientViewBeforeDelete(id);
  if(U?.role !== 'admin') return;
  const c = await api('/api/clients/'+id);
  const head = document.querySelector('#modalBox .modal-head');
  if(head && !head.querySelector('.delete-client-btn')){
    const actions = head.querySelector('.actions') || head;
    actions.insertAdjacentHTML('beforeend', `<button class="btn btn-bad delete-client-btn" onclick="deleteClient(${c.id},'${esc(c.name).replace(/'/g,'&#39;')}')">Excluir cliente</button>`);
  }
};

const _contractViewBeforeDelete = contractView;
contractView = async function(id){
  await _contractViewBeforeDelete(id);
  if(U?.role !== 'admin') return;
  const c = await api('/api/contracts/'+id);
  const head = document.querySelector('#modalBox .modal-head');
  if(head && !head.querySelector('.delete-contract-btn')){
    head.insertAdjacentHTML('beforeend', `<button class="btn btn-bad delete-contract-btn" onclick="deleteContract(${c.id},'${esc(c.number)}')">Excluir contrato</button>`);
  }
};

async function deleteContract(id, number){
  const expected = `EXCLUIR ${number}`;
  const typed = prompt(`ATENÇÃO: esta ação é permanente.\n\nO contrato, parcelas, pagamentos e movimentos financeiros ligados a ele serão removidos.\n\nDigite exatamente:\n${expected}`);
  if(typed === null) return;
  if(typed.trim().toUpperCase() !== expected.toUpperCase()){
    toast('Confirmação incorreta. Exclusão cancelada.');
    return;
  }
  const f = new FormData(); f.append('confirmation', typed);
  try{
    await api('/api/contracts/'+id,{method:'DELETE',body:f});
    closeModal();
    toast('Contrato excluído e caixa recalculado.');
    if(PAGE === 'contracts') await render_contracts(); else await go(PAGE);
  }catch(e){ toast(e.message); }
}

async function deleteClient(id, name){
  const expected = `EXCLUIR ${name}`;
  const typed = prompt(`ATENÇÃO: a ficha e os documentos do cliente serão apagados.\nClientes com contratos não podem ser excluídos até que os contratos sejam removidos.\n\nDigite exatamente:\n${expected}`);
  if(typed === null) return;
  if(typed.trim().toUpperCase() !== expected.toUpperCase()){
    toast('Confirmação incorreta. Exclusão cancelada.');
    return;
  }
  const f = new FormData(); f.append('confirmation', typed);
  try{
    await api('/api/clients/'+id,{method:'DELETE',body:f});
    closeModal();
    toast('Cliente excluído com sucesso.');
    if(PAGE === 'clients') await render_clients(); else await go(PAGE);
  }catch(e){ toast(e.message); }
}
