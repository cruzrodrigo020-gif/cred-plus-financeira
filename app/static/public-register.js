const form=document.getElementById('registerForm');
const btn=document.getElementById('submitBtn');
const msg=document.getElementById('message');
const selfie=document.getElementById('selfie');
const residenceProof=document.getElementById('residenceProof');
const MAX_IMAGE=5*1024*1024;

function validateImageInput(input,label){
  msg.textContent='';
  const file=input?.files?.[0];
  if(file&&file.size>MAX_IMAGE){
    input.value='';
    msg.textContent=`${label} deve ter no máximo 5 MB.`;
    return false;
  }
  return true;
}

selfie?.addEventListener('change',()=>validateImageInput(selfie,'A selfie'));
residenceProof?.addEventListener('change',()=>validateImageInput(residenceProof,'O comprovante de residência'));

form.addEventListener('submit',async e=>{
  e.preventDefault();
  msg.textContent='';
  const selfieFile=selfie?.files?.[0];
  const proofFile=residenceProof?.files?.[0];
  if(!selfieFile){
    msg.textContent='Envie uma selfie para concluir o cadastro.';
    return;
  }
  if(!proofFile){
    msg.textContent='Envie a foto do comprovante de residência para concluir o cadastro.';
    return;
  }
  if(selfieFile.size>MAX_IMAGE){
    msg.textContent='A selfie deve ter no máximo 5 MB.';
    return;
  }
  if(proofFile.size>MAX_IMAGE){
    msg.textContent='O comprovante de residência deve ter no máximo 5 MB.';
    return;
  }
  btn.disabled=true;
  btn.textContent='Enviando cadastro...';
  try{
    const data=new FormData(form);
    const r=await fetch('/api/public/clients',{method:'POST',body:data});
    const x=await r.json().catch(()=>({detail:'Não foi possível concluir o cadastro.'}));
    if(!r.ok){
      let detail=x.detail||'Não foi possível concluir o cadastro.';
      if(Array.isArray(detail)) detail=detail.map(v=>v.msg||'Campo inválido').join(' • ');
      throw new Error(detail);
    }
    form.classList.add('hidden');
    const pre=x.pre_analysis||{};
    const bandLabel={baixo:'BAIXO',medio:'MÉDIO',alto:'ALTO'}[pre.band]||'EM ANÁLISE';
    const result=document.getElementById('scoreResult');
    if(result){
      const limit=Number(pre.suggested_limit||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
      result.className='score-result '+(pre.band||'');
      result.innerHTML=`<span>Pré-score cadastral</span><strong>${bandLabel}</strong><b>${Number(pre.score||0)}/100 pontos</b><em>Limite indicativo: ${limit}</em>`;
    }
    document.getElementById('success').classList.remove('hidden');
    window.scrollTo({top:0,behavior:'smooth'});
  }catch(err){
    msg.textContent=err.message||'Erro ao enviar cadastro.';
    btn.disabled=false;
    btn.textContent='Enviar cadastro';
  }
});
