async function render_reports(){
  if(U.role!=='admin')return;
  const a=await api('/api/reports/contracts');
  const totalPrincipal=a.reduce((s,x)=>s+Number(x.principal||0),0);
  const totalReceived=a.reduce((s,x)=>s+Number(x.received||0),0);
  const totalBalance=a.reduce((s,x)=>s+Number(x.balance||0),0);
  $('content').innerHTML=`
    <div class="kpis" style="grid-template-columns:repeat(4,minmax(150px,1fr))">
      <div class="kpi"><div class="lab">Registros</div><div class="val">${a.length}</div></div>
      <div class="kpi"><div class="lab">Capital emprestado</div><div class="val">${money(totalPrincipal)}</div></div>
      <div class="kpi"><div class="lab">Total recebido</div><div class="val">${money(totalReceived)}</div></div>
      <div class="kpi"><div class="lab">Saldo a receber</div><div class="val">${money(totalBalance)}</div></div>
    </div>
    <div class="card">
      <div class="toolbar">
        <div><h2>📁 Arquivo de empréstimos em PDF</h2><div class="muted">Histórico completo dos empréstimos e acordos registrados no sistema.</div></div>
        <div class="actions">
          <button class="btn btn-primary" onclick="downloadAllContractsPdf()">⬇ PDF geral</button>
          <input class="search" placeholder="Buscar cliente, contrato ou tipo" oninput="filterRows('reportContractsBody',this.value)">
        </div>
      </div>
      <div class="table-wrap"><table>
        <tr><th>Data</th><th>Cliente</th><th>Contrato</th><th>Tipo</th><th>Valor</th><th>Juros</th><th>Total</th><th>Recebido</th><th>Saldo</th><th>Status</th><th>PDF</th></tr>
        <tbody id="reportContractsBody">${a.map(k=>`<tr>
          <td>${fmt(k.date)}</td>
          <td><b>${esc(k.client)}</b><br><span class="muted">${esc(k.cpf||'')}</span></td>
          <td>${esc(k.number)}</td>
          <td>${esc(k.type)}</td>
          <td>${money(k.principal)}</td>
          <td>${Number(k.rate||0).toFixed(2)}%</td>
          <td>${money(k.total)}</td>
          <td>${money(k.received)}</td>
          <td><b>${money(k.balance)}</b></td>
          <td><span class="badge active">${esc(k.status)}</span></td>
          <td><button class="btn btn-soft btn-xs" onclick="downloadContractPdf(${k.id},'${esc(k.number)}')">Baixar PDF</button></td>
        </tr>`).join('')||'<tr><td colspan="11" class="empty">Nenhum empréstimo cadastrado.</td></tr>'}</tbody>
      </table></div>
    </div>`;
}

async function downloadPdf(url,filename){
  try{
    const r=await fetch(url,{headers:{Authorization:'Bearer '+T}});
    if(!r.ok){
      let msg='Não foi possível gerar o PDF';
      try{const x=await r.json();msg=x.detail||msg}catch{}
      return toast(msg);
    }
    const b=await r.blob();
    const a=document.createElement('a');
    a.href=URL.createObjectURL(b);
    a.download=filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(()=>URL.revokeObjectURL(a.href),1500);
  }catch(e){toast(e.message||'Erro ao gerar PDF')}
}

function downloadAllContractsPdf(){
  return downloadPdf('/api/reports/contracts.pdf','cred-plus-relatorio-geral-emprestimos.pdf');
}

function downloadContractPdf(id,number){
  const safe=String(number||id).replace(/[^a-zA-Z0-9_-]/g,'-');
  return downloadPdf('/api/reports/contracts/'+id+'.pdf','emprestimo-'+safe+'.pdf');
}
