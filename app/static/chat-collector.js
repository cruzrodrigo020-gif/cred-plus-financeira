let COLLECTOR_CHAT_PEER=null;
let COLLECTOR_CHAT_TIMER=null;
let COLLECTOR_CHAT_CONTACTS=[];

const _collectorBaseNav=nav;
nav=function(){
  _collectorBaseNav();
  $('nav-chat')?.classList.toggle('active',PAGE==='chat');
};

const _collectorBaseGo=go;
go=async function(p){
  if(p!=='chat'){
    if(COLLECTOR_CHAT_TIMER){clearInterval(COLLECTOR_CHAT_TIMER);COLLECTOR_CHAT_TIMER=null;}
    return _collectorBaseGo(p);
  }
  PAGE='chat';
  nav();
  $('content').innerHTML='<div class="card muted">Carregando chat...</div>';
  try{await renderCollectorChat()}catch(e){$('content').innerHTML=`<div class="card alert">${esc(e.message)}</div>`}
};

function collectorChatTime(v){
  if(!v)return '';
  const d=new Date(v);
  if(Number.isNaN(d.getTime()))return '';
  const now=new Date();
  const same=d.toDateString()===now.toDateString();
  return `${same?'':d.toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})+' '}${d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}`;
}

async function collectorChatUnread(){
  if(!TOKEN||!USER)return;
  try{
    const x=await api('/api/chat/unread');
    const el=$('collectorChatBadge');
    if(!el)return;
    const n=Number(x.count||0);
    el.className=n?'cpchat-badge-nav':'';
    el.textContent=n?String(n):'';
  }catch{}
}

async function renderCollectorChat(){
  COLLECTOR_CHAT_CONTACTS=await api('/api/chat/contacts');
  if(!COLLECTOR_CHAT_PEER||!COLLECTOR_CHAT_CONTACTS.some(c=>Number(c.id)===Number(COLLECTOR_CHAT_PEER))){
    COLLECTOR_CHAT_PEER=COLLECTOR_CHAT_CONTACTS[0]?.id||null;
  }
  $('content').innerHTML=`<div class="collector-chat-wrap"><div class="hero"><div class="eyebrow">Chat interno</div><h1>Fale com a administração</h1><p>Mensagens internas da CRED+ Financeira.</p></div><section id="collectorChatConversation" class="cpchat-main">${COLLECTOR_CHAT_PEER?'<div class="cpchat-empty">Carregando conversa...</div>':'<div class="cpchat-empty">Nenhum administrador ativo disponível.</div>'}</section></div>`;
  if(COLLECTOR_CHAT_PEER)await loadCollectorChatMessages(true);
  if(COLLECTOR_CHAT_TIMER)clearInterval(COLLECTOR_CHAT_TIMER);
  COLLECTOR_CHAT_TIMER=setInterval(async()=>{
    if(PAGE!=='chat'){clearInterval(COLLECTOR_CHAT_TIMER);COLLECTOR_CHAT_TIMER=null;return;}
    try{await loadCollectorChatMessages(false);await collectorChatUnread()}catch{}
  },2500);
}

async function loadCollectorChatMessages(forceBottom=false){
  if(!COLLECTOR_CHAT_PEER)return;
  const x=await api(`/api/chat/messages/${COLLECTOR_CHAT_PEER}`);
  const host=$('collectorChatConversation');
  if(!host)return;
  const oldMessages=host.querySelector('.cpchat-messages');
  const nearBottom=!oldMessages||oldMessages.scrollHeight-oldMessages.scrollTop-oldMessages.clientHeight<90;
  const initials=String(x.peer?.name||'ADM').trim().split(/\s+/).slice(0,2).map(v=>v[0]||'').join('').toUpperCase();
  const select=COLLECTOR_CHAT_CONTACTS.length>1?`<select onchange="selectCollectorChat(this.value)" style="margin-left:auto;background:#091522;color:white;border:1px solid #213550;border-radius:10px;padding:8px">${COLLECTOR_CHAT_CONTACTS.map(c=>`<option value="${c.id}" ${Number(c.id)===Number(COLLECTOR_CHAT_PEER)?'selected':''}>${esc(c.name)}</option>`).join('')}</select>`:'';
  host.innerHTML=`<div class="cpchat-head"><div class="cpchat-avatar">${esc(initials)}</div><div><div class="cpchat-title">${esc(x.peer?.name||'Administração')}</div><div class="cpchat-sub">Administração • chat interno CRED+</div></div>${select}</div><div id="collectorChatMessages" class="cpchat-messages">${(x.messages||[]).map(m=>collectorChatBubble(m)).join('')||'<div class="cpchat-empty">Nenhuma mensagem ainda.<br>Envie a primeira mensagem.</div>'}</div><form class="cpchat-compose" onsubmit="sendCollectorChat(event)"><textarea id="collectorChatInput" maxlength="2000" placeholder="Digite uma mensagem..." onkeydown="collectorChatKey(event)"></textarea><button class="cpchat-send" type="submit">Enviar</button></form>`;
  const msgBox=$('collectorChatMessages');
  if(msgBox&&(forceBottom||nearBottom))msgBox.scrollTop=msgBox.scrollHeight;
  collectorChatUnread();
}

function collectorChatBubble(m){
  const mine=Number(m.sender_id)===Number(USER?.id);
  const checks=mine?(m.read_at?' ✓✓':' ✓'):'';
  return `<div class="cpchat-row ${mine?'mine':''}"><div class="cpchat-bubble">${esc(m.message)}<div class="cpchat-meta">${collectorChatTime(m.created_at)}${checks}</div></div></div>`;
}

async function selectCollectorChat(id){
  COLLECTOR_CHAT_PEER=Number(id);
  await loadCollectorChatMessages(true);
}

function collectorChatKey(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();e.target.form?.requestSubmit();}
}

async function sendCollectorChat(e){
  e?.preventDefault();
  if(!COLLECTOR_CHAT_PEER)return;
  const input=$('collectorChatInput');
  const text=String(input?.value||'').trim();
  if(!text)return;
  const f=new FormData();
  f.append('recipient_id',COLLECTOR_CHAT_PEER);
  f.append('message',text);
  try{
    await api('/api/chat/messages',{method:'POST',body:f});
    if(input)input.value='';
    await loadCollectorChatMessages(true);
  }catch(e){toast(e.message)}
}

setInterval(collectorChatUnread,8000);
