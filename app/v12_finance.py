from datetime import datetime, timedelta, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.v12_models import Product, Client, Contract, Installment, Payment, Cash
from app.v12_helpers import db, parse_date, current_user, require_admin, log, visible_contracts_query, make_receipt_pdf

router = APIRouter()

@router.get('/api/products')
def products(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    current_user(authorization, s)
    return [{'id': x.id, 'name': x.name, 'rate': x.rate, 'days': x.days, 'periodicity': x.periodicity}
            for x in s.query(Product).all()]


@router.get('/api/contracts')
def contracts(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    out = []
    for x in visible_contracts_query(s, u).order_by(Contract.id.desc()).all():
        client = s.get(Client, x.client_id)
        out.append({'id': x.id, 'number': x.number, 'client_id': x.client_id, 'client': client.name if client else '-',
                    'principal': x.principal, 'total': x.total, 'installments': x.installments,
                    'first_due': str(x.first_due), 'rate': x.rate, 'periodicity': x.periodicity, 'status': x.status})
    return out


@router.get('/api/contracts/{contract_id}')
def contract_detail(contract_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    c = s.get(Contract, contract_id)
    if not c:
        raise HTTPException(404, 'Contrato não encontrado')
    if u.role == 'collector' and c.collector_id != u.id:
        raise HTTPException(403, 'Contrato fora da sua carteira')
    client = s.get(Client, c.client_id)
    installments = s.query(Installment).filter_by(contract_id=c.id).order_by(Installment.number).all()
    return {
        'id': c.id, 'number': c.number, 'client': client.name if client else '-', 'client_id': c.client_id,
        'principal': c.principal, 'total': c.total, 'installments': c.installments, 'first_due': str(c.first_due),
        'rate': c.rate, 'periodicity': c.periodicity, 'status': c.status,
        'items': [
            {'id': i.id, 'number': i.number, 'due_date': str(i.due_date), 'amount': i.amount,
             'paid_amount': i.paid_amount, 'status': i.status, 'paid_at': str(i.paid_at) if i.paid_at else ''}
            for i in installments
        ]
    }


@router.post('/api/contracts')
def create_contract(
    client_id: int = Form(...), product_id: int = Form(...), principal: float = Form(...),
    installments: int = Form(...), first_due: str = Form(...), authorization: Optional[str] = Header(None),
    s: Session = Depends(db)
):
    u = current_user(authorization, s); require_admin(u)
    p = s.get(Product, product_id); c = s.get(Client, client_id)
    if not p or not c:
        raise HTTPException(404, 'Cliente/produto não encontrado')
    if principal <= 0 or installments <= 0:
        raise HTTPException(400, 'Valor e parcelas devem ser maiores que zero')
    due = parse_date(first_due, 'primeiro vencimento')
    n = 1 if p.periodicity == 'final' else installments
    total = round(principal * (1 + p.rate / 100), 2)
    values = []
    base = int((total / n) * 100) / 100
    running = 0.0
    for idx in range(n):
        value = base if idx < n - 1 else round(total - running, 2)
        values.append(value); running = round(running + value, 2)
    number = 'CTR-' + datetime.now().strftime('%y%m%d%H%M%S%f')[-12:]
    x = Contract(number=number, client_id=c.id, principal=principal, total=total, installments=n,
                 installment_value=round(total / n, 2), first_due=due, rate=p.rate,
                 periodicity=p.periodicity, product_id=p.id, collector_id=c.collector_id, status='active')
    s.add(x); s.flush()
    for idx, value in enumerate(values, 1):
        item_due = due if p.periodicity == 'final' else due + timedelta(days=idx - 1)
        s.add(Installment(contract_id=x.id, number=idx, due_date=item_due, amount=value, status='pending', paid_amount=0))
    s.add(Cash(kind='out', category='Crédito liberado', amount=principal, movement_date=date.today(),
               description=number, reference_id=number, user_id=u.id))
    s.commit(); log(s, u, 'CONTRACT_CREATE', number)
    return {'id': x.id, 'number': number}


@router.get('/api/installments')
def installments(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    q = s.query(Installment).join(Contract)
    if u.role == 'collector':
        q = q.filter(Contract.collector_id == u.id)
    out = []
    for i in q.order_by(Installment.due_date, Installment.number).all():
        c = s.get(Contract, i.contract_id); client = s.get(Client, c.client_id) if c else None
        out.append({'id': i.id, 'contract_id': i.contract_id, 'contract': c.number if c else '-',
                    'client': client.name if client else '-', 'client_id': client.id if client else None,
                    'number': i.number, 'due_date': str(i.due_date), 'amount': i.amount,
                    'status': i.status, 'paid_amount': i.paid_amount,
                    'paid_at': str(i.paid_at) if i.paid_at else ''})
    return out


@router.post('/api/installments/{installment_id}/mark-paid')
def mark_paid(
    installment_id: int, payment_date: str = Form(''), method: str = Form('PIX'),
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    u = current_user(authorization, s)
    i = s.get(Installment, installment_id)
    if not i:
        raise HTTPException(404, 'Parcela não encontrada')
    c = s.get(Contract, i.contract_id)
    if u.role == 'collector' and c.collector_id != u.id:
        raise HTTPException(403, 'Parcela fora da sua carteira')
    if i.status == 'paid' and i.paid_amount >= i.amount - 0.005:
        p = s.query(Payment).filter_by(installment_id=i.id).order_by(Payment.id.desc()).first()
        return {'ok': True, 'payment_id': p.id if p else None, 'already_paid': True}
    paid = parse_date(payment_date, 'data do pagamento', optional=True) or date.today()
    remaining = max(0, i.amount - i.paid_amount)
    collector = u.id if u.role == 'collector' else c.collector_id
    p = Payment(installment_id=i.id, contract_id=c.id, client_id=c.client_id, collector_id=collector,
                amount=remaining, payment_date=paid, method=method, note='Marcação rápida como paga')
    i.paid_amount = i.amount; i.paid_at = paid; i.status = 'paid'
    s.add(p); s.add(Cash(kind='in', category='Pagamento de parcela', amount=remaining, movement_date=paid,
                         description=f'{c.number} • Parcela {i.number}', reference_id=f'INST-{i.id}', user_id=u.id))
    s.commit(); s.refresh(p); log(s, u, 'INSTALLMENT_PAID', f'{c.number}/{i.number}')
    return {'ok': True, 'payment_id': p.id}


@router.post('/api/installments/{installment_id}/mark-unpaid')
def mark_unpaid(installment_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    i = s.get(Installment, installment_id)
    if not i:
        raise HTTPException(404, 'Parcela não encontrada')
    c = s.get(Contract, i.contract_id)
    if u.role == 'collector' and c.collector_id != u.id:
        raise HTTPException(403, 'Parcela fora da sua carteira')
    amount = i.paid_amount
    if amount > 0:
        s.add(Cash(kind='out', category='Estorno de pagamento', amount=amount, movement_date=date.today(),
                   description=f'{c.number} • Parcela {i.number}', reference_id=f'ESTORNO-INST-{i.id}', user_id=u.id))
        for p in s.query(Payment).filter_by(installment_id=i.id).all():
            s.delete(p)
    i.paid_amount = 0; i.paid_at = None; i.status = 'unpaid'
    s.commit(); log(s, u, 'INSTALLMENT_UNPAID', f'{c.number}/{i.number}')
    return {'ok': True}


@router.patch('/api/installments/{installment_id}/due-date')
def edit_due_date(
    installment_id: int, due_date: str = Form(...), authorization: Optional[str] = Header(None),
    s: Session = Depends(db)
):
    u = current_user(authorization, s); require_admin(u)
    i = s.get(Installment, installment_id)
    if not i: raise HTTPException(404, 'Parcela não encontrada')
    old = i.due_date; i.due_date = parse_date(due_date, 'vencimento'); s.commit()
    log(s, u, 'DUE_DATE_CHANGE', f'{installment_id}:{old}->{i.due_date}')
    return {'ok': True}


@router.get('/api/payments/{payment_id}/receipt.pdf')
def receipt_pdf(payment_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    p = s.get(Payment, payment_id)
    if not p: raise HTTPException(404, 'Pagamento não encontrado')
    c = s.get(Contract, p.contract_id)
    if u.role == 'collector' and c and c.collector_id != u.id:
        raise HTTPException(403, 'Pagamento fora da sua carteira')
    buf = make_receipt_pdf(p, s)
    return StreamingResponse(buf, media_type='application/pdf',
                             headers={'Content-Disposition': f'attachment; filename="recibo-{payment_id}.pdf"'})
