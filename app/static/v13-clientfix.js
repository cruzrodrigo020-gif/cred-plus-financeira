// Corrige campos opcionais do cadastro de clientes antes do envio.
// Campos numéricos vazios não devem chegar como string vazia ao FastAPI.
async function saveClient(e,id){
  e.preventDefault();
  const form=e.target;
  const f=new FormData(form);

  const name=String(f.get('name')||'').trim();
  if(!name){
    toast('Informe o nome do cliente.');
    return;
  }
  f.set('name',name);

  const incomeRaw=String(f.get('income')||'').trim().replace(',','.');
  const incomeNumber=Number(incomeRaw||0);
  f.set('income',Number.isFinite(incomeNumber)?String(incomeNumber):'0');

  const collectorRaw=String(f.get('collector_id')||'').trim();
  if(!collectorRaw){
    f.delete('collector_id');
  }else if(!/^\d+$/.test(collectorRaw)){
    toast('Cobrador inválido.');
    return;
  }

  const submitBtn=form.querySelector('button[type="submit"], .foot .btn-primary');
  if(submitBtn){submitBtn.disabled=true;submitBtn.textContent='Salvando...';}

  try{
    let r;
    if(id) r=await api('/api/clients/'+id,{method:'PATCH',body:f});
    else r=await api('/api/clients',{method:'POST',body:f});

    const cid=id||r.id;
    if(!cid) throw new Error('O servidor não retornou o código do cliente.');

    const photo=document.getElementById('photoFile')?.files?.[0];
    if(photo){
      const pf=new FormData();
      pf.append('category','photo');
      pf.append('file',photo);
      await api(`/api/clients/${cid}/attachments`,{method:'POST',body:pf});
    }

    const docs=Array.from(document.getElementById('docFiles')?.files||[]);
    for(const d of docs){
      const df=new FormData();
      df.append('category','document');
      df.append('file',d);
      await api(`/api/clients/${cid}/attachments`,{method:'POST',body:df});
    }

    closeModal();
    toast(id?'Ficha atualizada com sucesso':'Cliente cadastrado com sucesso');
    await render_clients();
  }catch(err){
    toast(err.message||'Não foi possível salvar o cliente.');
    if(submitBtn){submitBtn.disabled=false;submitBtn.textContent='Salvar ficha';}
  }
}
