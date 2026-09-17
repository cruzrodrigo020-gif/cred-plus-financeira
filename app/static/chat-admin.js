let ADMIN_CHAT_PEER=null;
let ADMIN_CHAT_TIMER=null;
let ADMIN_CHAT_CONTACTS=[];

const _baseRenderNav=renderNav;
renderNav=function(){
  _baseRenderNav();
  const nav=$('nav');
  if(!nav||nav.querySelector('[data-chat-nav]'))return;
  const sep=nav.querySelector('.sep');
  const btn=document.createElement('button');
  btn.setAttribute('data-chat-nav','1');
  btn.className=PAGE==='chat'?'active':'';
  btn.onclick=()=>go('chat');
  btn.innerHTML='💬 Chat <span id="adminChatNavBadge"></span>';
  if(sep)nav.insertBefore(btn,sep);else nav.appendChild(btn);
  refreshAdminChatBadge();
};

async function refreshAdminChatBadge(){
  if(!T||!U)return;
  try{
    const x=await api('/api/chat/unread');
    const el=$('adminChatNavBadge');
    if(!el)return;
    const n=Number(x.count||0);
    el.className=n?'cpchat-badge-nav':'';
    el.textContent=n?String(n):'';
  }catch{}
}

function adminChatTime(v){
  if(!v)return '';
  const d=new Date(v);
  if(Number.isNaN(d.getTime()))return '';
  const now=new Date();
  const same=d.toDateString()===now.toDateString();
  return `${same?'':d.toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})+' '}${d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}`;
}

function adminChatContactHtml(c){
  const active=Number(ADMIN_CHAT_PEER)===Number(c.id)?'active':'';
  const initials=String(c.name||'?').trim().split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase();
  return `<button class="cpchat-contact ${active}" onclick="selectAdminChat(${c.id})"><div class="cpchat-avatar">${esc(initials)}</div><div class="cpchat-contact-body"><div class="cpchat-contact-name"><span>${esc(c.name)}</span>${c.unread?`<span class="cpchat-unread">${c.unread}</span>`:''}</div><div class="cpchat-preview">${esc(c.last_message||'Nenhuma mensagem ainda')}</div></div></button>`;
}

async function render_chat(){
  if(ADMIN_CHAT_TIMER)clearInterval(ADMIN_CHAT_TIMER);
  $('title').textContent='Chat interno';
  ADMIN_CHAT_CONTACTS=await api('/api/chat/contacts');
  if(!ADMIN_CHAT_PEER||!ADMIN_CHAT_CONTACTS.some(c=>Number(c.id)===Number(ADMIN_CHAT_PEER))){
    ADMIN_CHAT_PEER=ADMIN_CHAT_CONTACTS[0]?.id||null;
  }
  $('content').innerHTML=`<div class="cpchat-shell"><section class="cpchat-side"><div class="cpchat-side-head"><h2>Conversas</h2><div class="muted">Administrador ↔ cobradores</div></div><div id="adminChatContacts" class="cpchat-contacts">${ADMIN_CHAT_CONTACTS.map(adminChatContactHtml).join('')||'<div class="cpchat-empty">Nenhum cobrador ativo cadastrado.</div>'}</div></section><section class="cpchat-main"><div id="adminChatConversation" class="cpchat-empty">Selecione um cobrador para começar a conversar.</div></section></div>`;
  if(ADMIN_CHAT_PEER)await loadAdminChatMessages(true);
  ADMIN_CHAT_TIMER=setInterval(async()=>{
    if(PAGE!=='chat'){clearInterval(ADMIN_CHAT_TIMER);ADMIN_CHAT_TIMER=null;return;}
    try{
      await loadAdminChatMessages(false);
      await refreshAdminChatContacts();
      await refreshAdminChatBadge();
    }catch{}
  },2500);
}

async function refreshAdminChatContacts(){
  ADMIN_CHAT_CONTACTS=await api('/api/chat/contacts');
  const box=$('adminChatContacts');
  if(box)box.innerHTML=ADMIN_CHAT_CONTACTS.map(adminChatContactHtml).join('')||'<div class="cpchat-empty">Nenhum cobrador ativo cadastrado.</div>';
}

async function selectAdminChat(id){
  ADMIN_CHAT_PEER=Number(id);
  await refreshAdminChatContacts();
  await loadAdminChatMessages(true);
}

async function loadAdminChatMessages(forceBottom=false){
  if(!ADMIN_CHAT_PEER)return;
  const x=await api(`/api/chat/messages/${ADMIN_CHAT_PEER}`);
  const host=$('adminChatConversation');
  if(!host)return;

  const oldMessages=host.querySelector('.cpchat-messages');
  const nearBottom=!oldMessages||oldMessages.scrollHeight-oldMessages.scrollTop-oldMessages.clientHeight<90;
  const messagesHtml=(x.messages||[]).map(m=>adminChatBubble(m)).join('')||'<div class="cpchat-empty">Nenhuma mensagem ainda.<br>Envie a primeira mensagem.</div>';
  const samePeer=String(host.dataset.peerId||'')===String(ADMIN_CHAT_PEER)&&!!host.querySelector('#adminChatInput');

  if(samePeer){
    const msgBox=$('adminChatMessages');
    if(msgBox){
      msgBox.innerHTML=messagesHtml;
      if(forceBottom||nearBottom)msgBox.scrollTop=msgBox.scrollHeight;
    }
    refreshAdminChatBadge();
    return;
  }

  const initials=String(x.peer?.name||'?').trim().split(/\s+/).slice(0,2).map(v=>v[0]||'').join('').toUpperCase();
  host.className='cpchat-main';
  host.dataset.peerId=String(ADMIN_CHAT_PEER);
  host.innerHTML=`<div class="cpchat-head"><div class="cpchat-avatar">${esc(initials)}</div><div><div class="cpchat-title">${esc(x.peer?.name||'Cobrador')}</div><div class="cpchat-sub">Cobrador • chat interno CRED+</div></div></div><div id="adminChatMessages" class="cpchat-messages">${messagesHtml}</div><form class="cpchat-compose" onsubmit="sendAdminChat(event)"><textarea id="adminChatInput" maxlength="2000" placeholder="Digite uma mensagem..." onkeydown="adminChatKey(event)"></textarea><button class="cpchat-send" type="submit">Enviar</button></form>`;
  const msgBox=$('adminChatMessages');
  if(msgBox&&(forceBottom||nearBottom))msgBox.scrollTop=msgBox.scrollHeight;
  refreshAdminChatBadge();
}

function adminChatBubble(m){
  const mine=Number(m.sender_id)===Number(U?.id);
  const checks=mine?(m.read_at?' ✓✓':' ✓'):'';
  return `<div class="cpchat-row ${mine?'mine':''}"><div class="cpchat-bubble">${esc(m.message)}<div class="cpchat-meta">${adminChatTime(m.created_at)}${checks}</div></div></div>`;
}

function adminChatKey(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();e.target.form?.requestSubmit();}
}

async function sendAdminChat(e){
  e?.preventDefault();
  if(!ADMIN_CHAT_PEER)return;
  const input=$('adminChatInput');
  const text=String(input?.value||'').trim();
  if(!text)return;
  const f=new FormData();
  f.append('recipient_id',ADMIN_CHAT_PEER);
  f.append('message',text);
  try{
    await api('/api/chat/messages',{method:'POST',body:f});
    if(input)input.value='';
    await loadAdminChatMessages(true);
    await refreshAdminChatContacts();
    $('adminChatInput')?.focus();
  }catch(err){toast(err.message)}
}

setInterval(refreshAdminChatBadge,8000);
setTimeout(()=>{
  if(U){
    renderNav();
    refreshAdminChatBadge();
  }
},100);
