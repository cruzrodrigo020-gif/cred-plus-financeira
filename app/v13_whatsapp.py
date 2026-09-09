from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Header
from sqlalchemy.orm import Session

from app.v12_models import Client, Contract, Installment, User
from app.v12_helpers import db, current_user, log

router = APIRouter()


def reminder_item(s: Session, i: Installment):
    c = s.get(Contract, i.contract_id)
    client = s.get(Client, c.client_id) if c else None
    collector = s.get(User, c.collector_id) if c and c.collector_id else None
    today_ = date.today()
    days_until = (i.due_date - today_).days
    remaining = max(0, float(i.amount or 0) - float(i.paid_amount or 0))
    return {
        'installment_id': i.id,
        'contract_id': c.id if c else None,
        'contract': c.number if c else '-',
        'collector_id': c.collector_id if c else None,
        'collector': collector.name if collector else 'Administração',
        'client_id': client.id if client else None,
        'client': client.name if client else '-',
        'whatsapp': client.whatsapp if client else '',
        'phone': client.phone if client else '',
        'installment': i.number,
        'due_date': str(i.due_date),
        'amount': remaining,
        'days_until': days_until,
        'stage': 'two_days' if days_until == 2 else 'one_day' if days_until == 1 else 'today' if days_until == 0 else 'other',
        'status': i.status,
    }


@router.get('/api/whatsapp/reminders')
def whatsapp_reminders(
    contract_id: Optional[int] = None,
    collector_id: Optional[int] = None,
    installment_id: Optional[int] = None,
    include_all: bool = False,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    u = current_user(authorization, s)
    q = s.query(Installment).join(Contract)

    if u.role == 'collector':
        q = q.filter(Contract.collector_id == u.id)
    elif collector_id:
        q = q.filter(Contract.collector_id == collector_id)

    if contract_id:
        q = q.filter(Installment.contract_id == contract_id)
    if installment_id:
        q = q.filter(Installment.id == installment_id)

    q = q.filter(Installment.status != 'paid')
    items = q.order_by(Installment.due_date, Installment.number).all()
    out = [reminder_item(s, i) for i in items]

    if not include_all and not installment_id:
        out = [x for x in out if 0 <= x['days_until'] <= 2]
    return out


@router.post('/api/whatsapp/log-open')
def log_whatsapp_open(
    installment_id: int = Form(...),
    stage: str = Form(...),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    u = current_user(authorization, s)
    i = s.get(Installment, installment_id)
    if not i:
        raise HTTPException(404, 'Parcela não encontrada')
    c = s.get(Contract, i.contract_id)
    if u.role == 'collector' and c and c.collector_id != u.id:
        raise HTTPException(403, 'Parcela fora da sua carteira')
    log(s, u, 'WHATSAPP_OPEN', f'installment={installment_id};stage={stage}')
    return {'ok': True}
