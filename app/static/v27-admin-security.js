async function render_security(){
 if(U?.role!=='admin'){ $('content').textContent='Acesso restrito ao administrador.';return;}
 $('content').innerHTML='<div class="card"><h2>Segurança e Senha</h2><p>A senha atual não pode ser visualizada. Defina uma nova senha confirmando sua identidade.</p><form id="securityForm"><div class="field"><label>Senha atual</label><input name="current_password" type="password"></div><div class="field"><label>Código de recuperação</label><input name="recovery_code" type="password"></div><div class="field"><label>Nova senha</label><input name="new_password" type="password" minlength="12" required></div><div class="field"><label>Confirme a nova senha</label><input id="securityConfirm" type="password" minlength="12" required></div><label><input id="securityShow" type="checkbox"> Mostrar nova senha</label><p><button class="btn btn-primary" type="submit">Salvar nova senha</button></p><p id="securityStatus"></p></form></div>';
 const form=document.getElementById('securityForm');
 document.getElementById('securityShow').addEventListener('change',e=>{for(const x of [form.elements.new_password,document.getElementById('securityConfirm')])x.type=e.target.checked?'text':'password';});
 form.addEventListener('submit',async e=>{
  e.preventDefault();
  const status=document.getElementById('securityStatus');
  const data=new FormData(form);
  if(data.get('new_password')!==document.getElementById('securityConfirm').value){status.textContent='As senhas não coincidem.';return;}
  if(!data.get('current_password')&&!data.get('recovery_code')){status.textContent='Informe a senha atual ou o código de recuperação.';return;}
  data.set('username','admin');
  const button=form.querySelector('button[type=submit]');button.disabled=true;
  try{
   const res=await fetch('/api/password-recovery',{method:'POST',body:data});
   const result=await res.json();
   if(!res.ok)throw Error(result.detail||'Falha ao redefinir senha');
   status.textContent='Senha alterada. Use a nova senha no próximo acesso.';form.reset();
  }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
 });
}
