from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.v12_models import Base, engine, Client, Contract, Installment
from app.v12_helpers import db, current_user, require_admin, log

router = APIRouter()


class ContractLateFeeRule(Base):
    __tablename__ = 'contract_late_fee_rules'
    __table_args__ = (UniqueConstraint('contract_id', name='uq_contract_late_fee_rule'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    amount_per_day: Mapped[float] = mapped_column(Float, default=5.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Base.metadata.create_all(engine)


def contract_delinquency_row(s: Session, contract: Contract, today_: date):
    client = s.get(Client, contract.client_id)
    items = s.query(Installment).filter(
        Installment.contract_id == contract.id,
        Installment.status != 'paid',
    ).all()
    overdue = [i for i in items if i.due_date < today_]
    if not overdue:
        return None

    earliest_due = min(i.due_date for i in overdue)
    days_overdue = max(0, (today_ - earliest_due).days)
    overdue_balance = round(sum(max(0, i.amount - i.paid_amount) for i in overdue), 2)
    contract_balance = round(sum(max(0, i.amount - i.paid_amount) for i in items), 2)

    rule = s.query(ContractLateFeeRule).filter_by(contract_id=contract.id).first()
    enabled = bool(rule and rule.enabled)
    amount_per_day = float(rule.amount_per_day if rule else 5.0)
    late_fee = round(days_overdue * amount_per_day, 2) if enabled else 0.0
    updated_overdue = round(overdue_balance + late_fee, 2)

    return {
        'contract_id': contract.id,
        'contract': contract.number,
        'client_id': client.id if client else None,
        'client': client.name if client else '-',
        'whatsapp': (client.whatsapp or client.phone) if client else '',
        'periodicity': contract.periodicity,
        'principal': contract.principal,
        'contract_total': contract.total,
        'first_due': str(contract.first_due),
        'earliest_overdue_due': str(earliest_due),
        'days_overdue': days_overdue,
        'overdue_installments': len(overdue),
        'overdue_balance': overdue_balance,
        'contract_balance': contract_balance,
        'late_fee_enabled': enabled,
        'late_fee_per_day': amount_per_day,
        'late_fee_amount': late_fee,
        'updated_overdue_amount': updated_overdue,
    }


@router.get('/api/delinquency/contracts')
def delinquent_contracts(
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    user = current_user(authorization, s)
    today_ = date.today()
    q = s.query(Contract).filter(Contract.status == 'active')
    if user.role != 'admin':
        q = q.filter(Contract.collector_id == user.id)

    rows = []
    for contract in q.order_by(Contract.id.desc()).all():
        row = contract_delinquency_row(s, contract, today_)
        if row:
            rows.append(row)

    rows.sort(key=lambda x: (x['days_overdue'], x['updated_overdue_amount']), reverse=True)
    return {
        'date': str(today_),
        'contracts': rows,
        'contracts_count': len(rows),
        'overdue_balance': round(sum(x['overdue_balance'] for x in rows), 2),
        'late_fee_total': round(sum(x['late_fee_amount'] for x in rows), 2),
        'updated_overdue_total': round(sum(x['updated_overdue_amount'] for x in rows), 2),
    }


@router.post('/api/delinquency/contracts/{contract_id}/late-fee')
def set_contract_late_fee(
    contract_id: int,
    enabled: bool = Form(...),
    amount_per_day: float = Form(5.0),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    user = current_user(authorization, s)
    require_admin(user)

    contract = s.get(Contract, contract_id)
    if not contract or contract.status != 'active':
        raise HTTPException(404, 'Empréstimo ativo não encontrado')
    if amount_per_day < 0:
        raise HTTPException(400, 'O valor diário não pode ser negativo')

    today_ = date.today()
    row = contract_delinquency_row(s, contract, today_)
    if not row:
        raise HTTPException(400, 'Este empréstimo não possui parcela vencida')

    rule = s.query(ContractLateFeeRule).filter_by(contract_id=contract_id).first()
    if not rule:
        rule = ContractLateFeeRule(contract_id=contract_id)
        s.add(rule)
    rule.enabled = bool(enabled)
    rule.amount_per_day = float(amount_per_day)
    s.commit()

    log(s, user, 'CONTRACT_LATE_FEE', f'{contract.number}: enabled={enabled}; per_day={amount_per_day}')
    return contract_delinquency_row(s, contract, today_)
