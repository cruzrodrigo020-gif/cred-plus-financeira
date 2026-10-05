async function render_analytics(){
  const [x,d]=await Promise.all([
    api('/api/analytics/delinquency'),
    api('/api/delinquency/contracts')
  ]);
  const maxDaily=Math.max(1,...(x.daily_forecast||[]).map(v=>Number(v.amount||0)));
  const collectors=U.role==='admin'?`<div class="chart-card"><div class="chart-head"><div><h3>Risco por cobrador</h3><div class="muted">Carteiras ordenadas pelo valor vencido.</div></div></div>${barRows((x.collectors||[]).map(c=>({label:c.name,amount:c.amount})),true)}</div>`:'';

  const rows=(d.contracts||[]).map(r=>`<tr>
    <td><b>${esc(r.client)}</b><br><span class="muted">${esc(r.contract)}</span></td>
    <td>${fmt(r.earliest_overdue_due)}<br><span class="badge overdue">${r.days_overdue} dia(s)</span></td>
    <td>${r.overdue_installments}</td>
    <td><b>${money(r.overdue_balance)}</b><br><span class="muted">Saldo do contrato: ${money(r.contract_balance)}</span></td>
    <td>${r.late_fee_enabled?`<span class="badge overdue">R$ 5,00/dia ativo</span><br><b>${money(r.late_fee_amount)}</b>`:'<span class="muted">Não aplicado</span>'}</td>
    <td><b>${money(r.updated_overdue_amount)}</b></td>
    <td><div class="actions">
      <button class="btn btn-soft btn-xs" onclick="contractView(${r.contract_id})">Abrir</button>
      ${U.role==='admin'?(r.late_fee_enabled
        ?`<button class="btn btn-bad btn-xs" onclick="setLateFee(${r.contract_id},false)">Desativar R$ 5/dia</button>`
        :`<button class="btn btn-warn btn-xs" onclick="setLateFee(${r.contract_id},true)">+ R$ 5/dia</button>`):''}
      ${r.whatsapp?`<button class="btn wa-btn btn-xs" onclick="window.open('${waHref(r.whatsapp)}','_blank')">WhatsApp</button>`:''}
    </div></td>
  </tr>`).join('');

  $('content').innerHTML=`
    <div class="kpis" style="grid-template-columns:repeat(4,1fr)">
      <div class="kpi"><div class="lab">Total a receber</div><div class="val">${money(x.receivable_total)}</div></div>
      <div class="kpi metric-danger"><div class="lab">Total vencido</div><div class="val">${money(d.overdue_balance)}</div></div>
      <div class="kpi metric-warn"><div class="lab">Empréstimos vencidos</div><div class="val">${d.contracts_count||0}</div></div>
      <div class="kpi metric-danger"><div class="lab">Vencido + acréscimos</div><div class="val">${money(d.updated_overdue_total)}</div></div>
    </div>

    <div class="card">
      <div class="toolbar">
        <div><h2>⚠️ Empréstimos inadimplentes</h2><div class="muted">Veja os empréstimos vencidos, dias em atraso, saldo e o valor atualizado.</div></div>
        <div class="mini"><div class="t">Acréscimos ativos</div><div class="v" style="font-size:18px">${money(d.late_fee_total)}</div></div>
      </div>
      <div class="hint-box"><b>R$ 5,00 por dia:</b> o botão ativa uma regra por empréstimo. O valor é calculado automaticamente conforme os dias de atraso e não é somado novamente ao clicar várias vezes.</div>
      <div class="table-wrap"><table>
        <tr><th>Cliente / empréstimo</th><th>Vencimento / atraso</th><th>Parcelas vencidas</th><th>Valor vencido</th><th>Acréscimo diário</th><th>Valor atualizado</th><th>Ações</th></tr>
        <tbody>${rows||'<tr><td colspan="7" class="empty">Nenhum empréstimo vencido no momento.</td></tr>'}</tbody>
      </table></div>
    </div>

    <div class="card"><div class="toolbar"><div><h2>Previsão de recebimentos</h2><div class="muted">Baseada nas parcelas ainda abertas e respectivas datas de vencimento.</div></div></div>
      <div class="forecast-grid">${(x.forecast||[]).map(f=>`<div class="forecast-box"><div class="k">Próximos ${f.days} dias</div><div class="v">${money(f.amount)}</div></div>`).join('')}</div>
      <div class="chart-card" style="margin-top:14px"><div class="chart-head"><div><h3>Próximos 14 dias</h3><div class="muted">Volume previsto por dia.</div></div></div><div class="spark-bars">${(x.daily_forecast||[]).map(v=>`<div class="spark-col" title="${fmt(v.date)} • ${money(v.amount)}"><div class="spark-bar" style="height:${Math.max(3,Number(v.amount||0)/maxDaily*145)}px"></div><div class="spark-label">${fmt(v.date).slice(0,5)}</div></div>`).join('')}</div></div>
    </div>

    <div class="charts">
      <div class="chart-card"><div class="chart-head"><div><h3>Idade dos atrasos</h3><div class="muted">Quanto mais antiga a faixa, maior a atenção necessária.</div></div></div>${barRows(x.aging||[],true)}</div>
      <div class="chart-card"><div class="chart-head"><div><h3>Recebimentos dos últimos 6 meses</h3><div class="muted">Histórico efetivamente recebido.</div></div></div>${barRows(x.monthly_receipts||[])}</div>
      ${collectors}
    </div>`;
}

async function setLateFee(contractId,enabled){
  const msg=enabled
    ?'Ativar acréscimo de R$ 5,00 por dia de atraso neste empréstimo? O sistema calculará automaticamente desde o primeiro vencimento em aberto.'
    :'Desativar o acréscimo de R$ 5,00 por dia neste empréstimo?';
  if(!confirm(msg))return;
  const f=new FormData();
  f.append('enabled',enabled?'true':'false');
  f.append('amount_per_day','5');
  try{
    await api('/api/delinquency/contracts/'+contractId+'/late-fee',{method:'POST',body:f});
    toast(enabled?'R$ 5,00 por dia ativado':'Acréscimo diário desativado');
    await render_analytics();
  }catch(e){toast(e.message)}
}
