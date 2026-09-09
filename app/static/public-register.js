const form=document.getElementById('registerForm');
const btn=document.getElementById('submitBtn');
const msg=document.getElementById('message');
const selfie=document.getElementById('selfie');
const MAX_SELFIE=5*1024*1024;

selfie?.addEventListener('change',()=>{
  msg.textContent='';
  const file=selfie.files?.[0];
  if(file&&file.size>MAX_SELFIE){
    selfie.value='';
    msg.textContent='A selfie deve ter no máximo 5 MB.';
  }
});

form.addEventListener('submit',async e=>{
  e.preventDefault();
  msg.textContent='';
  const file=selfie?.files?.[0];
  if(!file){
    msg.textContent='Envie uma selfie para concluir o cadastro.';
    return;
  }
  if(file.size>MAX_SELFIE){
    msg.textContent='A selfie deve ter no máximo 5 MB.';
    return;
  }
  btn.disabled=true;
  btn.textContent='Enviando cadastro...';
  try{
    const data=new FormData(form);
    const r=await fetch('/api/public/clients',{method:'POST',body:data});
    const x=await r.json().catch(()=>({detail:'Não foi possível concluir o cadastro.'}));
    if(!r.ok) throw new Error(x.detail||'Não foi possível concluir o cadastro.');
    form.classList.add('hidden');
    document.getElementById('success').classList.remove('hidden');
    window.scrollTo({top:0,behavior:'smooth'});
  }catch(err){
    msg.textContent=err.message||'Erro ao enviar cadastro.';
    btn.disabled=false;
    btn.textContent='Enviar cadastro';
  }
});
