import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.v12_helpers import db, current_user, require_admin
from app.v15_lender import LenderAccount, LenderSubscription, LenderSubscriptionPayment, current_lender_unrestricted, ensure_lender_subscription

router=APIRouter()
PRICE=24.99
PIX_KEY=os.getenv('SUBSCRIPTION_PIX_KEY','')
MAX_PROOF=5*1024*1024

def status_data(s,account):
    sub=ensure_lender_subscription(s,account)
    now=datetime.utcnow()
    paid=bool(sub.paid_until and sub.paid_until>now)
    trial=bool(sub.trial_ends_at>now and not paid)
    active=paid or trial
    phase='active' if paid else ('trial' if trial else 'expired')
    until=sub.paid_until if paid else sub.trial_ends_at
    pending=s.query(LenderSubscriptionPayment).filter_by(lender_id=account.id,status='pending').order_by(LenderSubscriptionPayment.id.desc()).first()
    seconds=max(0,int((until-now).total_seconds())) if until else 0
    return {'active':active,'phase':phase,'days_left':(seconds+86399)//86400 if seconds else 0,'trial_ends_at':sub.trial_ends_at.isoformat(),'paid_until':sub.paid_until.isoformat() if sub.paid_until else '','access_until':until.isoformat() if until else '','price':PRICE,'billing_cycle':'mensal','pix_key':PIX_KEY,'pending_payment':bool(pending),'pending_payment_id':pending.id if pending else None,'account_name':account.name}

@router.get('/api/lender/subscription/status')
def sub_status(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    return status_data(s,current_lender_unrestricted(authorization,s))

@router.post('/api/lender/subscription/payment')
async def send_payment(proof:UploadFile=File(...),authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    account=current_lender_unrestricted(authorization,s)
    if s.query(LenderSubscriptionPayment).filter_by(lender_id=account.id,status='pending').first():
        raise HTTPException(409,'Já existe um comprovante aguardando aprovação.')
    data=await proof.read()
    if not data: raise HTTPException(400,'Envie o comprovante do pagamento.')
    if len(data)>MAX_PROOF: raise HTTPException(400,'O comprovante deve ter no máximo 5 MB.')
    ct=(proof.content_type or '').lower()
    if not(ct.startswith('image/') or ct=='application/pdf'): raise HTTPException(400,'Envie o comprovante em imagem ou PDF.')
    p=LenderSubscriptionPayment(lender_id=account.id,amount=PRICE,status='pending',proof_filename=(proof.filename or 'comprovante')[:255],proof_content_type=(proof.content_type or 'application/octet-stream')[:120],proof_size=len(data),proof_data=data)
    s.add(p);s.commit();s.refresh(p)
    return {'ok':True,'id':p.id,'message':'Comprovante enviado. Aguarde a aprovação.'}

@router.get('/api/admin/subscriptions')
def admin_list(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=current_user(authorization,s);require_admin(u)
    rows=[]
    for account in s.query(LenderAccount).order_by(LenderAccount.id.desc()).all():
        st=status_data(s,account)
        pending=s.query(LenderSubscriptionPayment).filter_by(lender_id=account.id,status='pending').order_by(LenderSubscriptionPayment.id.desc()).first()
        rows.append({'account_id':account.id,'name':account.name,'email':account.email,'whatsapp':account.whatsapp,'created_at':account.created_at.isoformat() if account.created_at else '',**st,'pending_id':pending.id if pending else None,'pending_created_at':pending.created_at.isoformat() if pending and pending.created_at else ''})
    return rows

@router.get('/api/admin/subscriptions/payments/{payment_id}/proof')
def proof_file(payment_id:int,authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=current_user(authorization,s);require_admin(u)
    p=s.get(LenderSubscriptionPayment,payment_id)
    if not p or not p.proof_data: raise HTTPException(404,'Comprovante não encontrado.')
    return Response(content=p.proof_data,media_type=p.proof_content_type or 'application/octet-stream')

@router.post('/api/admin/subscriptions/payments/{payment_id}/approve')
def approve(payment_id:int,authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=current_user(authorization,s);require_admin(u)
    p=s.get(LenderSubscriptionPayment,payment_id)
    if not p: raise HTTPException(404,'Pagamento não encontrado.')
    if p.status!='pending': raise HTTPException(400,'Este pagamento já foi analisado.')
    account=s.get(LenderAccount,p.lender_id)
    sub=ensure_lender_subscription(s,account);now=datetime.utcnow()
    base=sub.paid_until if sub.paid_until and sub.paid_until>now else now
    sub.paid_until=base+timedelta(days=30);sub.status='active'
    p.status='approved';p.reviewed_at=now;p.reviewed_by=u.id
    s.commit()
    return {'ok':True,'paid_until':sub.paid_until.isoformat()}

@router.post('/api/admin/subscriptions/payments/{payment_id}/reject')
def reject(payment_id:int,authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=current_user(authorization,s);require_admin(u)
    p=s.get(LenderSubscriptionPayment,payment_id)
    if not p: raise HTTPException(404,'Pagamento não encontrado.')
    if p.status!='pending': raise HTTPException(400,'Este pagamento já foi analisado.')
    p.status='rejected';p.reviewed_at=datetime.utcnow();p.reviewed_by=u.id;s.commit()
    return {'ok':True}
