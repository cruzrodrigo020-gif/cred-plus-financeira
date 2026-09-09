const form=document.getElementById('registerForm');
const btn=document.getElementById('submitBtn');
const msg=document.getElementById('message');

form.addEventListener('submit',async e=>{
  e.preventDefault();
  msg.textContent='';
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
