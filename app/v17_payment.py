from datetime import datetime, timedelta, date
import calendar
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Header
from sqlalchemy import Date, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.v12_models import Base, engine, Product, Client, Contract, Installment, Payment, Cash
from app.v12_helpers import db, parse_date, current_user, require_admin, log

router = APIRouter()


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class ContractRenewal(Base):
    __tablename__ = 'contract_renewals'
    id: Mapped[int] = mapped_column(primary_key=True)
    old_contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), index=True)
    new_contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), index=True)
    interest_paid: Mapped[float] = mapped_column(Float, default=0)
    renewal_date: Mapped[date] = mapped_column(Date)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)


def _money(v):
    return round(float(v or 0), 2)


def _contract_received(s: Session, contract_id: int):
    return _money(sum(float(p.amount or 0) for p in s.query(Payment).filter_by(contract_id=contract_id).all()))


def _split_values(total: float, count: int):
    count = max(1, int(count or 1))
    total = _money(total)
    total_cents = int(round(total * 100))
    base_cents = total_cents // count
    values = []
    running = 0
    for idx in range(count):
        cents = base_cents if idx < count - 1 else total_cents - running
        values.append(cents / 100)
        running += cents
    return values


@router.get('/api/installments/extended')
def installments_extended(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    q = s.query(Installment).join(Contract).filter(Contract.status == 'active')
    if u.role == 'collector':
        q = q.filter(Contract.collector_id == u.id)
    out = []
    for i in q.order_by(Installment.due_date, Installment.number).all():
        c = s.get(Contract, i.contract_id)
        client = s.get(Client, c.client_id) if c else None
        out.append({
            'id': i.id, 'contract_id': i.contract_id, 'contract': c.number if c else '-',
            'contract_status': c.status if c else '', 'client': client.name if client else '-',
            'client_id': client.id if client else None, 'number': i.number, 'due_date': str(i.due_date),
            'amount': _money(i.amount), 'paid_amount': _money(i.paid_amount),
            'remaining': _money(max(0, float(i.amount or 0) - float(i.paid_amount or 0))),
            'status': i.status, 'paid_at': str(i.paid_at) if i.paid_at else '',
            'principal': _money(c.principal) if c else 0, 'rate': _money(c.rate) if c else 0,
            'interest_due': _money((c.principal or 0) * (c.rate or 0) / 100) if c else 0,
        })
    return out


@router.post('/api/installments/{installment_id}/partial-payment')
def partial_payment(
    installment_id: int, amount: float = Form(...), payment_date: str = Form(''),
    method: str = Form('PIX'), note: str = Form('Pagamento parcial'),
    authorization: Optional[str] = Header(None), s: Session = Depends(db),
):
    u = current_user(authorization, s)
    require_admin(u)
    i = s.get(Installment, installment_id)
    if not i:
        raise HTTPException(404, 'Parcela n?o encontrada')
    c = s.get(Contract, i.contract_id)
    if not c or c.status != 'active':
        raise HTTPException(400, 'Este contrato n?o est? ativo')

    remaining = _money(max(0, float(i.amount or 0) - float(i.paid_amount or 0)))
    amount = _money(amount)
    if remaining <= 0:
        raise HTTPException(400, 'Esta parcela j? est? quitada')
    if amount <= 0:
        raise HTTPException(400, 'Informe um valor maior que zero')
    if amount > remaining + 0.005:
        raise HTTPException(400, f'O valor parcial n?o pode ultrapassar o saldo de R$ {remaining:.2f}')

    paid = parse_date(payment_date, 'data do pagamento', optional=True) or date.today()
    p = Payment(
        installment_id=i.id, contract_id=c.id, client_id=c.client_id, collector_id=c.collector_id,
        amount=amount, payment_date=paid, method=(method or 'PIX')[:30],
        note=(note or 'Pagamento parcial')[:1000],
    )
    i.paid_amount = _money(float(i.paid_amount or 0) + amount)
    new_remaining = _money(max(0, float(i.amount or 0) - float(i.paid_amount or 0)))
    if new_remaining <= 0.005:
        i.paid_amount = _money(i.amount)
        i.status = 'paid'
        i.paid_at = paid
        new_remaining = 0
    else:
        i.status = 'partial'
        i.paid_at = None

    s.add(p)
    s.add(Cash(
        kind='in', category='Pagamento parcial', amount=amount, movement_date=paid,
        description=f'{c.number} o Parcela {i.number} o Parcial',
        reference_id=f'PARCIAL-INST-{i.id}', user_id=u.id,
    ))
    s.commit()
    s.refresh(p)
    log(s, u, 'INSTALLMENT_PARTIAL', f'{c.number}/{i.number}:R${amount:.2f}')
    return {'ok': True, 'payment_id': p.id, 'paid_amount': _money(i.paid_amount),
            'remaining': new_remaining, 'status': i.status}


@router.get('/api/contracts/{contract_id}/renewal-preview')
def renewal_preview(contract_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    require_admin(u)
    c = s.get(Contract, contract_id)
    if not c:
        raise HTTPException(404, 'Contrato n?o encontrado')
    if c.status != 'active':
        raise HTTPException(400, 'Somente contratos ativos podem ser renovados')
    interest_due = _money(float(c.principal or 0) * float(c.rate or 0) / 100)
    received = _contract_received(s, c.id)
    if received > interest_due + 0.01:
        raise HTTPException(400, 'Este contrato j? recebeu valor acima dos juros. A renova??o por juros n?o se aplica.')
    remaining_interest = _money(max(0, interest_due - received))
    p = s.get(Product, c.product_id)
    if c.periodicity == 'monthly':
        recommended = _add_months(date.today(), 1)
    else:
        recommended = date.today() + timedelta(days=(p.days if c.periodicity == 'final' and p else 1))
    return {
        'contract_id': c.id, 'contract': c.number, 'principal': _money(c.principal), 'rate': _money(c.rate),
        'interest_due': interest_due, 'already_received': received,
        'interest_to_pay_now': remaining_interest, 'installments': c.installments,
        'periodicity': c.periodicity, 'recommended_first_due': str(recommended),
    }


@router.post('/api/contracts/{contract_id}/renew-interest')
def renew_interest(
    contract_id: int, first_due: str = Form(...), payment_date: str = Form(''),
    method: str = Form('PIX'), authorization: Optional[str] = Header(None), s: Session = Depends(db),
):
    u = current_user(authorization, s)
    require_admin(u)
    c = s.get(Contract, contract_id)
    if not c:
        raise HTTPException(404, 'Contrato n?o encontrado')
    if c.status != 'active':
        raise HTTPException(400, 'Somente contratos ativos podem ser renovados')
    client = s.get(Client, c.client_id)
    if not client:
        raise HTTPException(404, 'Cliente n?o encontrado')

    interest_due = _money(float(c.principal or 0) * float(c.rate or 0) / 100)
    received = _contract_received(s, c.id)
    if received > interest_due + 0.01:
        raise HTTPException(400, 'O contrato j? recebeu mais do que os juros. N?o ? poss?vel renovar como pagamento somente de juros.')
    remaining_interest = _money(max(0, interest_due - received))
    paid_date = parse_date(payment_date, 'data do pagamento', optional=True) or date.today()
    due = parse_date(first_due, 'novo primeiro vencimento')
    if due < paid_date:
        raise HTTPException(400, 'O novo vencimento n?o pode ser anterior ? data da renova??o')

    payment_id = None
    if remaining_interest > 0:
        first_item = s.query(Installment).filter_by(contract_id=c.id).order_by(Installment.number).first()
        if not first_item:
            raise HTTPException(400, 'Contrato sem parcelas para vincular o pagamento dos juros')
        pmt = Payment(
            installment_id=first_item.id, contract_id=c.id, client_id=c.client_id,
            collector_id=c.collector_id, amount=remaining_interest, payment_date=paid_date,
            method=(method or 'PIX')[:30], note='Pagamento de juros para renova??o do empr?stimo',
        )
        s.add(pmt)
        s.flush()
        payment_id = pmt.id
        s.add(Cash(
            kind='in', category='Juros de renova??o', amount=remaining_interest, movement_date=paid_date,
            description=f'{c.number} o Juros para renova??o', reference_id=f'RENEW-{c.number}', user_id=u.id,
        ))

    for item in s.query(Installment).filter_by(contract_id=c.id).all():
        if item.status != 'paid':
            item.status = 'renewed'
    c.status = 'renewed'

    total = _money(float(c.principal or 0) * (1 + float(c.rate or 0) / 100))
    count = max(1, int(c.installments or 1))
    values = _split_values(total, count)
    number = 'REN-' + datetime.now().strftime('%y%m%d%H%M%S%f')[-12:]
    new_contract = Contract(
        number=number, client_id=c.client_id, principal=_money(c.principal), total=total,
        installments=count, installment_value=_money(total / count), first_due=due, rate=_money(c.rate),
        periodicity=c.periodicity, product_id=c.product_id, collector_id=c.collector_id, status='active',
    )
    s.add(new_contract)
    s.flush()
    for idx, value in enumerate(values, 1):
        if c.periodicity == 'final':
            item_due = due
        elif c.periodicity == 'monthly':
            item_due = _add_months(due, idx - 1)
        else:
            item_due = due + timedelta(days=idx - 1)
        s.add(Installment(contract_id=new_contract.id, number=idx, due_date=item_due,
                          amount=value, status='pending', paid_amount=0))

    s.add(ContractRenewal(
        old_contract_id=c.id, new_contract_id=new_contract.id, interest_paid=interest_due,
        renewal_date=paid_date, created_by=u.id,
    ))
    s.commit()
    s.refresh(new_contract)
    log(s, u, 'CONTRACT_RENEW_INTEREST',
        f'{c.number}->{new_contract.number};juros=R${interest_due:.2f};principal=R${c.principal:.2f}')
    return {
        'ok': True, 'old_contract_id': c.id, 'new_contract_id': new_contract.id,
        'new_contract': new_contract.number, 'principal': _money(new_contract.principal),
        'new_total': _money(new_contract.total), 'interest_paid': interest_due, 'payment_id': payment_id,
    }
