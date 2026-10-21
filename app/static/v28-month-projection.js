
let MONTH_PROJECTION=null;

function projectionRows(title, data, kind){
  const headers=kind==='sales'
    ? '<tr><th>Vencimento</th><th>Cliente</th><th>Contrato</th><th>Produto</th><th>Parcela</th><th>A receber</th></tr>'
    : '<tr><th>Vencimento</th><th>Cliente</th><th>Contrato</th><th>Modalidade</th><th>Parcela</th><th>Saldo da parcela</th><th>Juros estimados</th><th>Capital estimado</th></tr>';
  const rows=data.items.map(function(x){
    const base='<td>'+fmt(x.date)+'</td><td>'+esc(x.client)+'</td><td>'+esc(x.contract)+'</td>';
    if(kind==='sales'){
      return '<tr>'+base+'<td>'+esc(x.product||'-')+'</td><td>'+x.installment+'</td><td><b>'+money(x.amount)+'</b></td></tr>';
    }
    const label=x.periodicity==='monthly'?'Acordo mensal':x.periodicity==='weekly'?'Semanal':x.periodicity==='final'?'Pagamento final':'Diário';
    return '<tr>'+base+'<td>'+label+' ('+Number(x.rate).toFixed(2)+'%)</td><td>'+x.installment+'</td><td>'+money(x.amount)+'</td><td><b>'+money(x.interest)+'</b></td><td>'+money(x.capital)+'</td></tr>';
  }).join('');
  const colspan=kind==='sales'?6:8;
  const footer=kind==='loans'
    ? 'Capital previsto: '+money(data.capital)+' + juros previstos: '+money(data.interest)+' = total dos empréstimos: '+money(data.gross)
    : kind==='agreements'
      ? 'A receber: '+money(data.total)+' | Juros estimados embutidos: '+money(data.interest)+' | Capital estimado: '+money(data.capital)
      : 'Parcelas de vendas a receber: '+money(data.total)+' (não representa lucro)';
  return '<div class="card"><div class="toolbar"><div><h2>'+title+'</h2><div class="muted">'+data.count+' parcela(s) de '+data.contracts+' contrato(s) • Vencidos antes de hoje, fora da previsão: '+money(data.overdue)+'</div></div></div>'
    +'<div class="muted" style="margin-bottom:12px">'+footer+'</div>'
    +'<div class="table-wrap"><table>'+headers+(rows||'<tr><td colspan="'+colspan+'" class="empty">Sem parcelas previstas neste período.</td></tr>')+'</table></div></div>';
}

function projectionClientTable(data){
  const map=new Map();
  for(const [category, group] of [['loans',data.loans],['agreements',data.agreements],['sales',data.sales]]){
    for(const item of group.items){
      const key=item.client;
      if(!map.has(key))map.set(key,{client:key,loans:0,loanCapital:0,agreements:0,sales:0});
      const r=map.get(key);
      r[category]+=category==='loans'?Number(item.interest):Number(item.amount);
      if(category==='loans')r.loanCapital+=Number(item.capital);
    }
  }
  const rows=Array.from(map.values()).sort((a,b)=>a.client.localeCompare(b.client,'pt-BR')).map(x=>
    '<tr><td>'+esc(x.client)+'</td><td>'+money(x.loanCapital)+'</td><td>'+money(x.loans)+'</td><td><b>'+money(x.loanCapital+x.loans)+'</b></td><td>'+money(x.agreements)+'</td><td>'+money(x.sales)+'</td><td><b>'+money(x.loanCapital+x.loans+x.agreements+x.sales)+'</b></td></tr>'
  ).join('');
  return '<div class="card"><h2>Resumo por cliente</h2><div class="table-wrap"><table><tr><th>Cliente</th><th>Capital dos empréstimos</th><th>Juros dos empréstimos</th><th>Total dos empréstimos</th><th>Acordos a receber</th><th>Vendas a receber</th><th>Total geral a receber</th></tr>'
    +(rows||'<tr><td colspan="7">Sem clientes com vencimentos no período.</td></tr>')
    +'</table></div></div>';
}

function projectionDailyTable(data){
  const rows=data.daily.map(x=>'<tr><td>'+fmt(x.date)+'</td><td>'+money(x.loans_capital)+'</td><td>'+money(x.loans_interest)+'</td><td><b>'+money(x.loans_gross)+'</b></td><td>'+money(x.agreements)+'</td><td>'+money(x.sales)+'</td><td><b>'+money(x.total_gross)+'</b></td></tr>').join('');
  return '<div class="card"><h2>Previsão diária de recebimentos</h2><div class="table-wrap"><table><tr><th>Data</th><th>Capital empréstimos</th><th>Juros empréstimos</th><th>Total empréstimos</th><th>Acordos</th><th>Vendas</th><th>Total geral</th></tr>'
    +(rows||'<tr><td colspan="7">Nenhum vencimento futuro neste mês.</td></tr>')+'</table></div></div>';
}

function exportMonthProjection(){
  if(!MONTH_PROJECTION)return;
  const d=MONTH_PROJECTION;
  const lines=[['Categoria','Cliente','Contrato','Parcela','Vencimento','Saldo bruto (R$)','Juros estimados (R$)','Capital estimado (R$)','Produto']];
  const clean=value=>{
    const v=String(value??'');
    // Avoid spreadsheet formula execution on CSV opened with Excel.
    const safe=/^[=+@\-\t\r]/.test(v)?"'"+v:v;
    return '"'+safe.replace(/"/g,'""')+'"';
  };
  for(const [kind, group] of [['Empréstimo',d.loans],['Acordo',d.agreements],['Venda',d.sales]]){
    for(const x of group.items){
      lines.push([kind,x.client,x.contract,x.installment,x.date,
        Number(x.amount).toFixed(2).replace('.',','),
        kind==='Venda'?'':Number(x.interest).toFixed(2).replace('.',','),
        kind==='Venda'?'':Number(x.capital).toFixed(2).replace('.',','),
        x.product||'']);
    }
  }
  const csv='\uFEFF'+lines.map(row=>row.map(clean).join(';')).join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  const anchor=document.createElement('a');
  anchor.href=url;anchor.download='cred-mais-projecao-'+d.as_of.slice(0,7)+'.csv';
  anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

async function render_projection(){
  if(U?.role!=='admin'){
    $('content').innerHTML='<div class="card">Área restrita ao administrador.</div>';return;
  }
  $('content').innerHTML='<div class="card"><div class="muted">Calculando projeção a partir dos contratos e parcelas...</div></div>';
  const d=await api('/api/projections/month-end');
  MONTH_PROJECTION=d;
  const legend='<p class="muted">Os números são previsões de recebimento, não pagamentos garantidos. Os juros são estimados proporcionalmente em cada parcela. Valores já pagos e parcelas vencidas antes de '+fmt(d.as_of)+' não entram na projeção.</p>';
  $('content').innerHTML=
    '<div class="card"><div class="toolbar"><div><h2>📈 Projeção financeira até '+fmt(d.through)+'</h2><div class="muted">Período: '+fmt(d.as_of)+' a '+fmt(d.through)+' • atualizado com os registros atuais</div></div><div class="actions"><button class="btn btn-soft" onclick="render_projection()">Atualizar</button><button class="btn btn-primary" onclick="exportMonthProjection()">Exportar CSV</button></div></div>'
    +legend+'</div>'
    +'<div class="kpis">'
    +'<div class="kpi"><div class="lab">Capital previsto • empréstimos</div><div class="val">'+money(d.loans.capital)+'</div><div class="muted">Devolução do valor emprestado</div></div>'
    +'<div class="kpi"><div class="lab">Juros previstos • empréstimos</div><div class="val">'+money(d.loans.interest)+'</div><div class="muted">Receita estimada de juros</div></div>'
    +'<div class="kpi"><div class="lab">Total dos empréstimos (capital + juros)</div><div class="val">'+money(d.loans.gross)+'</div><div class="muted">Parcelas de empréstimos a receber até o fim do mês</div></div>'
    +'<div class="kpi"><div class="lab">Acordos a receber</div><div class="val">'+money(d.agreements.total)+'</div><div class="muted">Juros estimados: '+money(d.agreements.interest)+'</div></div>'
    +'<div class="kpi"><div class="lab">Parcelas de vendas</div><div class="val">'+money(d.sales.total)+'</div><div class="muted">Receita bruta, não lucro</div></div>'
    +'<div class="kpi"><div class="lab">Total geral a receber</div><div class="val">'+money(d.total_projected_gross)+'</div><div class="muted">Empréstimos (capital + juros) + acordos + vendas</div></div>'
    +'<div class="kpi"><div class="lab">Total sem capital dos empréstimos</div><div class="val">'+money(d.total_projected)+'</div><div class="muted">Juros dos empréstimos + acordos integrais + vendas integrais; não é lucro líquido</div></div>'
    +'</div>'
    +projectionDailyTable(d)
    +projectionClientTable(d)
    +projectionRows('Empréstimos: somente juros previstos',d.loans,'loans')
    +projectionRows('Acordos: parcelas e juros estimados',d.agreements,'agreements')
    +projectionRows('Vendas: parcelas previstas',d.sales,'sales')
    +'<div class="card"><h2>Parcelas vencidas (fora da projeção)</h2><p>Empréstimos: <b>'+money(d.loans.overdue)+'</b> • Acordos: <b>'+money(d.agreements.overdue)+'</b> • Vendas: <b>'+money(d.sales.overdue)+'</b></p><p class="muted">Esses saldos estão atrasados e não foram somados aos recebimentos com vencimento até o fim do mês. Eles podem ser recuperados, mas a data do recebimento é incerta.</p></div>';
}


/* Atalho e resumo discreto na Dashboard, sem alterar as contas existentes. */
const _renderDashboardBeforeProjection=render_dashboard;
render_dashboard=async function(){
  await _renderDashboardBeforeProjection();
  if(U?.role!=='admin')return;
  const root=$('content');
  if(!root)return;
  const card=document.createElement('div');
  card.className='card';
  card.innerHTML='<div class="toolbar"><div><h2>📈 Projeção de recebimentos até o fim do mês</h2><div class="muted" id="projectionDashboardSummary">Calculando a previsão...</div></div><button class="btn btn-primary" onclick="go(\'projection\')">Ver relatório detalhado</button></div>';
  root.prepend(card);
  try{
    const d=await api('/api/projections/month-end');
    const el=document.getElementById('projectionDashboardSummary');
    if(el)el.textContent='Empréstimos: capital '+money(d.loans.capital)+' + juros '+money(d.loans.interest)+' = '+money(d.loans.gross)+' | Acordos: '+money(d.agreements.total)+' | Vendas: '+money(d.sales.total)+' | Total geral: '+money(d.total_projected_gross);
  }catch(e){
    const el=document.getElementById('projectionDashboardSummary');
    if(el)el.textContent='Não foi possível consultar a projeção agora. Acesse o relatório para tentar novamente.';
  }
};
