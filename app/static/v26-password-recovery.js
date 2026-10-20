function togglePasswordRecovery(){
  const el=document.getElementById('passwordRecoveryForm');
  el.classList.toggle('hidden');
  if(!el.classList.contains('hidden')) el.querySelector('[name="username"]').focus();
}
async function submitPasswordRecovery(event){
  event.preventDefault();
  const form=event.currentTarget;
  const msg=document.getElementById('recoveryMsg');
  const data=new FormData(form);
  if(data.get('new_password')!==document.getElementById('confirmRecoveryPassword').value){
    msg.textContent='As novas senhas não coincidem.';
    return;
  }
  if(!data.get('current_password')&&!data.get('recovery_code')){
    msg.textContent='Informe a senha atual ou o código de recuperação.';
    return;
  }
  const button=form.querySelector('button[type="submit"]');
  button.disabled=true;
  msg.textContent='Verificando...';
  try{
    const response=await fetch('/api/password-recovery',{method:'POST',body:data});
    const result=await response.json();
    if(!response.ok)throw new Error(result.detail||'Não foi possível redefinir a senha.');
    msg.textContent=result.message||'Senha redefinida com sucesso.';
    document.getElementById('loginUser').value=data.get('username');
    form.reset();
  }catch(error){
    msg.textContent=error.message;
  }finally{
    button.disabled=false;
  }
}
