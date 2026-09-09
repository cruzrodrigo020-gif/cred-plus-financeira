from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form, Header
from sqlalchemy.orm import Session
from app.v12_models import User, Client, Contract, Installment, Payment, Cash, Closing, pwd
from app.v12_helpers import db, parse_date, current_user, require_admin, log

router = APIRouter()

@router.get('/api/cash')
def cash_list(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    require_admin(u)
    return [{'id': x.id, 'kind': x.kind, 'category': x.category, 'amount': x.amount,
             'movement_date': str(x.movement_date), 'description': x.description, 'reference_id': x.reference_id}
            for x in s.query(Cash).order_by(Cash.id.desc()).limit(500).all()]


@router.post('/api/cash/expense')
def expense(
    amount: float = Form(...), movement_date: str = Form(''), description: str = Form(''),
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    u = current_user(authorization, s); require_admin(u)
    if amount <= 0: raise HTTPException(400, 'Valor inválido')
    d = parse_date(movement_date, 'data', optional=True) or date.today()
    s.add(Cash(kind='out', category='Despesa', amount=amount, movement_date=d, description=description, user_id=u.id))
    s.commit(); log(s, u, 'EXPENSE', str(amount)); return {'ok': True}


@router.post('/api/cash/entry')
def cash_entry(
    amount: float = Form(...), movement_date: str = Form(''), description: str = Form('Aporte de capital'),
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    u = current_user(authorization, s); require_admin(u)
    if amount <= 0: raise HTTPException(400, 'Valor inválido')
    d = parse_date(movement_date, 'data', optional=True) or date.today()
    s.add(Cash(kind='in', category='Aporte de capital', amount=amount, movement_date=d, description=description, user_id=u.id))
    s.commit(); log(s, u, 'CASH_ENTRY', str(amount)); return {'ok': True}


@router.get('/api/users')
def users(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s); require_admin(u)
    return [{'id': x.id, 'name': x.name, 'username': x.username, 'role': x.role, 'active': x.active}
            for x in s.query(User).order_by(User.name).all()]


@router.post('/api/users')
def create_user(
    name: str = Form(...), username: str = Form(...), password: str = Form(...), role: str = Form('collector'),
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    u = current_user(authorization, s); require_admin(u)
    if role not in ('admin', 'collector'): raise HTTPException(400, 'Perfil inválido')
    if len(password) < 8: raise HTTPException(400, 'A senha deve ter pelo menos 8 caracteres')
    if s.query(User).filter_by(username=username).first(): raise HTTPException(409, 'Usuário já existe')
    x = User(name=name, username=username, password_hash=pwd.hash(password), role=role, active=True)
    s.add(x); s.commit(); s.refresh(x); log(s, u, 'USER_CREATE', username)
    return {'id': x.id}


@router.get('/api/collectors/summary')
def collectors_summary(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s); require_admin(u)
    today_ = date.today(); out = []
    for c in s.query(User).filter_by(role='collector').order_by(User.name).all():
        clients_count = s.query(Client).filter_by(collector_id=c.id).count()
        contracts_count = s.query(Contract).filter_by(collector_id=c.id, status='active').count()
        received = sum(p.amount for p in s.query(Payment).filter_by(collector_id=c.id, payment_date=today_).all())
        overdue = sum(max(0, i.amount - i.paid_amount) for i in s.query(Installment).join(Contract).filter(
            Contract.collector_id == c.id, Installment.status != 'paid', Installment.due_date < today_).all())
        out.append({'id': c.id, 'name': c.name, 'clients': clients_count, 'contracts': contracts_count,
                    'received_today': received, 'overdue': overdue})
    return out


@router.get('/api/closings')
def closings(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    q = s.query(Closing)
    if u.role == 'collector': q = q.filter(Closing.collector_id == u.id)
    return [{'id': x.id, 'collector_id': x.collector_id,
             'collector': (s.get(User, x.collector_id).name if s.get(User, x.collector_id) else '-'),
             'closing_date': str(x.closing_date), 'expected': x.expected, 'received': x.received,
             'declared': x.declared, 'difference': x.difference, 'notes': x.notes, 'status': x.status}
            for x in q.order_by(Closing.closing_date.desc(), Closing.id.desc()).limit(200).all()]


@router.post('/api/closings')
def create_closing(
    closing_date: str = Form(''), declared: float = Form(...), notes: str = Form(''),
    collector_id: Optional[int] = Form(None), authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    u = current_user(authorization, s)
    d = parse_date(closing_date, 'data do fechamento', optional=True) or date.today()
    cid = collector_id if u.role == 'admin' and collector_id else u.id
    collector = s.get(User, cid)
    if not collector or collector.role != 'collector':
        raise HTTPException(400, 'Cobrador inválido')
    received = sum(p.amount for p in s.query(Payment).filter_by(collector_id=cid, payment_date=d).all())
    difference = round(declared - received, 2)
    x = Closing(collector_id=cid, closing_date=d, expected=received, received=received,
                declared=declared, difference=difference, notes=notes, status='closed')
    s.add(x); s.commit(); s.refresh(x); log(s, u, 'CLOSING_CREATE', f'{cid}:{d}')
    return {'id': x.id, 'received': received, 'difference': difference}
