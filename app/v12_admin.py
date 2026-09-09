from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form, Header
from sqlalchemy.orm import Session
from app.v12_models import User, Client, Contract, Installment, Payment, Cash, Closing, pwd
from app.v12_helpers import db, parse_date, current_user, require_admin, log

router = APIRouter()


def _collector_or_404(s: Session, collector_id: int):
    collector = s.get(User, collector_id)
    if not collector or collector.role != 'collector':
        raise HTTPException(404, 'Cobrador não encontrado')
    return collector


def _collector_metrics(s: Session, collector: User):
    today_ = date.today()
    month_start = today_.replace(day=1)

    clients = s.query(Client).filter_by(collector_id=collector.id).all()
    contracts = s.query(Contract).filter_by(collector_id=collector.id, status='active').all()
    installments = s.query(Installment).join(Contract).filter(Contract.collector_id == collector.id).all()

    pending = [i for i in installments if i.status != 'paid']
    today_items = [i for i in installments if i.due_date == today_]
    overdue_items = [i for i in pending if i.due_date < today_]

    receivable = sum(max(0, i.amount - i.paid_amount) for i in pending)
    due_today = sum(max(0, i.amount - i.paid_amount) for i in today_items if i.status != 'paid')
    scheduled_today = sum(i.amount for i in today_items)
    overdue = sum(max(0, i.amount - i.paid_amount) for i in overdue_items)

    received_today = sum(
        p.amount for p in s.query(Payment).filter_by(collector_id=collector.id, payment_date=today_).all()
    )
    received_month = sum(
        p.amount for p in s.query(Payment).filter(
            Payment.collector_id == collector.id,
            Payment.payment_date >= month_start,
            Payment.payment_date <= today_,
        ).all()
    )

    collected_due_today = sum(
        p.amount for p in s.query(Payment).join(Installment, Payment.installment_id == Installment.id).filter(
            Payment.collector_id == collector.id,
            Payment.payment_date == today_,
            Installment.due_date == today_,
        ).all()
    )
    collection_rate = round(min(100, (collected_due_today / scheduled_today * 100)) if scheduled_today else 0, 1)

    last_closing = s.query(Closing).filter_by(collector_id=collector.id).order_by(
        Closing.closing_date.desc(), Closing.id.desc()
    ).first()

    return {
        'id': collector.id,
        'name': collector.name,
        'username': collector.username,
        'active': collector.active,
        'clients': len(clients),
        'contracts': len(contracts),
        'received_today': round(received_today, 2),
        'received_month': round(received_month, 2),
        'due_today': round(due_today, 2),
        'due_today_count': sum(1 for i in today_items if i.status != 'paid'),
        'overdue': round(overdue, 2),
        'overdue_count': len(overdue_items),
        'receivable': round(receivable, 2),
        'collection_rate': collection_rate,
        'last_closing_date': str(last_closing.closing_date) if last_closing else '',
        'last_closing_difference': last_closing.difference if last_closing else 0,
    }


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
    return [_collector_metrics(s, c) for c in s.query(User).filter_by(role='collector').order_by(User.name).all()]


@router.get('/api/collectors/{collector_id}')
def collector_detail(collector_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s); require_admin(u)
    collector = _collector_or_404(s, collector_id)
    metrics = _collector_metrics(s, collector)
    today_ = date.today()

    client_rows = []
    for c in s.query(Client).filter_by(collector_id=collector.id).order_by(Client.name).all():
        contracts = s.query(Contract).filter_by(client_id=c.id).all()
        installments = s.query(Installment).join(Contract).filter(
            Contract.client_id == c.id, Installment.status != 'paid'
        ).order_by(Installment.due_date).all()
        overdue_items = [i for i in installments if i.due_date < today_]
        next_due = installments[0].due_date if installments else None
        client_rows.append({
            'id': c.id,
            'name': c.name,
            'cpf': c.cpf,
            'whatsapp': c.whatsapp,
            'phone': c.phone,
            'city': c.city,
            'contracts': len(contracts),
            'receivable': round(sum(max(0, i.amount - i.paid_amount) for i in installments), 2),
            'overdue': round(sum(max(0, i.amount - i.paid_amount) for i in overdue_items), 2),
            'overdue_count': len(overdue_items),
            'next_due': str(next_due) if next_due else '',
        })

    today_rows = []
    for i in s.query(Installment).join(Contract).filter(
        Contract.collector_id == collector.id,
        Installment.due_date == today_,
    ).order_by(Installment.number).all():
        contract = s.get(Contract, i.contract_id)
        client = s.get(Client, contract.client_id) if contract else None
        today_rows.append({
            'id': i.id,
            'client_id': client.id if client else None,
            'client': client.name if client else '-',
            'whatsapp': client.whatsapp if client else '',
            'contract': contract.number if contract else '-',
            'number': i.number,
            'due_date': str(i.due_date),
            'amount': i.amount,
            'paid_amount': i.paid_amount,
            'status': i.status,
        })

    overdue_rows = []
    for i in s.query(Installment).join(Contract).filter(
        Contract.collector_id == collector.id,
        Installment.status != 'paid',
        Installment.due_date < today_,
    ).order_by(Installment.due_date).limit(100).all():
        contract = s.get(Contract, i.contract_id)
        client = s.get(Client, contract.client_id) if contract else None
        overdue_rows.append({
            'id': i.id,
            'client_id': client.id if client else None,
            'client': client.name if client else '-',
            'whatsapp': client.whatsapp if client else '',
            'contract': contract.number if contract else '-',
            'number': i.number,
            'due_date': str(i.due_date),
            'amount': i.amount,
            'paid_amount': i.paid_amount,
            'remaining': round(max(0, i.amount - i.paid_amount), 2),
            'days_overdue': (today_ - i.due_date).days,
            'status': i.status,
        })

    unassigned = [
        {'id': c.id, 'name': c.name, 'cpf': c.cpf, 'whatsapp': c.whatsapp, 'city': c.city}
        for c in s.query(Client).filter(Client.collector_id.is_(None)).order_by(Client.name).all()
    ]

    return {
        'collector': metrics,
        'clients': client_rows,
        'today_items': today_rows,
        'overdue_items': overdue_rows,
        'unassigned_clients': unassigned,
    }


@router.post('/api/collectors/{collector_id}/assign-client')
def assign_client(
    collector_id: int,
    client_id: int = Form(...),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    u = current_user(authorization, s); require_admin(u)
    collector = _collector_or_404(s, collector_id)
    client = s.get(Client, client_id)
    if not client:
        raise HTTPException(404, 'Cliente não encontrado')
    old_collector = client.collector_id
    client.collector_id = collector.id
    for contract in s.query(Contract).filter_by(client_id=client.id).all():
        contract.collector_id = collector.id
    s.commit()
    log(s, u, 'CLIENT_COLLECTOR_CHANGE', f'{client.id}:{old_collector}->{collector.id}')
    return {'ok': True, 'collector_id': collector.id, 'collector': collector.name}


@router.post('/api/collectors/{collector_id}/remove-client')
def remove_client(
    collector_id: int,
    client_id: int = Form(...),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    u = current_user(authorization, s); require_admin(u)
    _collector_or_404(s, collector_id)
    client = s.get(Client, client_id)
    if not client:
        raise HTTPException(404, 'Cliente não encontrado')
    if client.collector_id != collector_id:
        raise HTTPException(400, 'Este cliente não pertence a esse cobrador')
    client.collector_id = None
    for contract in s.query(Contract).filter_by(client_id=client.id).all():
        contract.collector_id = None
    s.commit()
    log(s, u, 'CLIENT_COLLECTOR_REMOVE', f'{client.id}:{collector_id}->None')
    return {'ok': True}


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
