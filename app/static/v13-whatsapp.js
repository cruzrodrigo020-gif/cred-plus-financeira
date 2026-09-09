function cpWaNumber(phone){
  let n=String(phone||'').replace(/\D/g,'');
  if(!n)return '';
  if(n.startsWith('55'))return n;
  if(n.length===10||n.length===11)return '55'+n;
  return n;
}

function cpReminderStageForDays(days){
  if(days===2)return 'two_days';
  if(days===1)return 'one_day';
  if(days===0)return 'today';
  return 'other';
}

function cpReminderLabel(stage){
  return stage==='two_days'?'2 dias antes':stage==='one_day'?'1 dia antes':stage==='today'?'No vencimento':'Aviso';
}

function cpReminderMessage(item,stage){
  const name=(item.client||'Cliente').trim();
  const value=money(item.amount||0);
  const due=fmt(item.due_date);
  const parcel=item.installment;
  const contract=item.contract||'';
  if(stage==='two_days'){
    return `Olá, ${name}! Tudo bem? Aqui é da CRED+ Financeira. Passando para lembrar que a parcela ${parcel} do seu empréstimo, referente ao contrato ${contract}, no valor de ${value}, vence em ${due}, daqui a 2 dias. Se o pagamento já tiver sido realizado, desconsidere esta mensagem. Em caso de dúvida, fale conosco.`;
  }
  if(stage==='one_day'){
    return `Olá, ${name}! Tudo bem? Aqui é da CRED+ Financeira. Este é um lembrete de que a parcela ${parcel} do seu empréstimo, referente ao contrato ${contract}, no valor de ${value}, vence amanhã, ${due}. Se o pagamento já tiver sido realizado, desconsidere esta mensagem. Em caso de dúvida, fale conosco.`;
  }
  return `Olá, ${name}! Tudo bem? Aqui é da CRED+ Financeira. Passando para lembrar que a parcela ${parcel} do seu empréstimo, referente ao contrato ${contract}, no valor de ${value}, vence hoje, ${due}. Se o pagamento já tiver sido realizado, desconsidere esta mensagem. Em caso de dúvida, fale conosco.`;
}

async function cpOpenWhatsAppReminder(installmentId,stage){
  try{
    const a=await api(`/api/whatsapp/reminders?installment_id=${installmentId}&include_all=true`);
    const item=a[0];
    if(!item)return toast('Parcela não encontrada');
    const expected=cpReminderStageForDays(Number(item.days_until));
    if(stage!==expected)return toast('Este aviso só é liberado na data correta.');
    const phone=cpWaNumber(item.whatsapp||item.phone);
    if(!phone)return toast('Cliente sem WhatsApp/telefone cadastrado.');
    const f=new FormData();f.append('installment_id',String(installmentId));f.append('stage',stage);
    api('/api/whatsapp/log-open',{method:'POST',body:f}).catch(()=>{});
    const text=encodeURIComponent(cpReminderMessage(item,stage));
    window.open(`https://wa.me/${phone}?text=${text}`,'_blank');
  }catch(e){toast(e.message)}
}

function cpReminderButtons(item){
  const expected=cpReminderStageForDays(Number(item.days_until));
  const phone=cpWaNumber(item.whatsapp||item.phone);
  const disabled=!phone;
  const stages=[['two_days','2 dias antes'],['one_day','1 dia antes'],['today','Hoje']];
  return `<div class="wa-reminder-actions">${stages.map(([stage,label])=>{
    const active=stage===expected && !disabled;
    const title=disabled?'Cliente sem WhatsApp cadastrado':active?'Aviso liberado para hoje':'Disponível somente na data correta';
    return `<button class="btn btn-xs ${active?'wa-reminder-active':'wa-reminder-disabled'}" ${active?'': 'disabled'} title="${title}" onclick="cpOpenWhatsAppReminder(${item.installment_id},'${stage}')">${active?'📲':'🔒'} ${label}</button>`;
  }).join('')}</div>`;
}

function cpReminderTiming(item){
  const d=Number(item.days_until);
  if(d===2)return '<span class="badge pending">Enviar hoje • 2 dias antes</span>';
  if(d===1)return '<span class="badge pending">Enviar hoje • 1 dia antes</span>';
  if(d===0)return '<span class="badge overdue">Vence hoje</span>';
  if(d>2)return `<span class="muted">Aviso abre em ${d-2} dia(s)</span>`;
  return '<span class="muted">Vencimento já passou</span>';
}

async function cpAppendContractReminders(contractId){
  const box=document.getElementById('modalBox');
  if(!box)return;
  const items=await api(`/api/whatsapp/reminders?contract_id=${contractId}&include_all=true`);
  const sec=document.createElement('div');
  sec.className='form-section wa-reminder-section';
  sec.innerHTML=`<div class="form-title">Avisos de vencimento pelo WhatsApp</div><div class="muted" style="margin-bottom:10px">Os três avisos ficam disponíveis automaticamente apenas no dia correto: 2 dias antes, 1 dia antes e no vencimento.</div><div class="table-wrap"><table><tr><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Momento do aviso</th><th>WhatsApp</th></tr>${items.map(i=>`<tr><td><b>${String(i.installment).padStart(2,'0')}</b></td><td>${fmt(i.due_date)}</td><td>${money(i.amount)}</td><td>${cpReminderTiming(i)}</td><td>${cpReminderButtons(i)}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">Nenhuma parcela aberta neste empréstimo.</td></tr>'}</table></div>`;
  box.appendChild(sec);
}

async function cpAppendCollectorReminders(collectorId){
  const box=document.getElementById('modalBox');
  if(!box)return;
  const items=await api(`/api/whatsapp/reminders?collector_id=${collectorId}`);
  const sec=document.createElement('div');
  sec.className='form-section wa-reminder-section';
  sec.innerHTML=`<div class="form-title">Avisos WhatsApp para enviar hoje</div><div class="muted" style="margin-bottom:10px">Clientes desta carteira que precisam receber aviso 2 dias antes, 1 dia antes ou hoje.</div><div class="table-wrap"><table><tr><th>Cliente</th><th>Contrato</th><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Aviso</th></tr>${items.map(i=>`<tr><td><b>${esc(i.client)}</b></td><td>${esc(i.contract)}</td><td>${i.installment}</td><td>${fmt(i.due_date)}</td><td>${money(i.amount)}</td><td><button class="btn btn-xs wa-reminder-active" onclick="cpOpenWhatsAppReminder(${i.installment_id},'${i.stage}')">📲 ${cpReminderLabel(i.stage)}</button></td></tr>`).join('')||'<tr><td colspan="6" class="empty">Nenhum aviso de vencimento para enviar hoje.</td></tr>'}</table></div>`;
  box.appendChild(sec);
}

async function cpUpcomingReminderCard(){
  const items=await api('/api/whatsapp/reminders');
  const root=document.getElementById('content');
  if(!root)return;
  const card=document.createElement('div');
  card.className='card wa-reminder-dashboard';
  card.innerHTML=`<div class="toolbar"><div><h2>📲 Avisos WhatsApp de vencimento</h2><div class="muted">Lembretes liberados para envio hoje.</div></div><span class="badge pending">${items.length} aviso(s)</span></div><div class="table-wrap"><table><tr><th>Cliente</th><th>Contrato</th><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Ação</th></tr>${items.map(i=>`<tr><td><b>${esc(i.client)}</b></td><td>${esc(i.contract)}</td><td>${i.installment}</td><td>${fmt(i.due_date)}</td><td>${money(i.amount)}</td><td><button class="btn btn-xs wa-reminder-active" onclick="cpOpenWhatsAppReminder(${i.installment_id},'${i.stage}')">📲 ${cpReminderLabel(i.stage)}</button></td></tr>`).join('')||'<tr><td colspan="6" class="empty">Nenhum aviso para hoje.</td></tr>'}</table></div>`;
  root.prepend(card);
}

if(typeof contractView==='function'){
  const cpBaseContractView=contractView;
  contractView=async function(id){await cpBaseContractView(id);try{await cpAppendContractReminders(id)}catch(e){toast(e.message)}};
}
if(typeof collectorView==='function'){
  const cpBaseCollectorView=collectorView;
  collectorView=async function(id){await cpBaseCollectorView(id);try{await cpAppendCollectorReminders(id)}catch(e){toast(e.message)}};
}
if(typeof render_installments==='function'){
  const cpBaseRenderInstallments=render_installments;
  render_installments=async function(){await cpBaseRenderInstallments();try{await cpUpcomingReminderCard()}catch(e){toast(e.message)}};
}
