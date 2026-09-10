from datetime import date, datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Form, Header, HTTPException
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.v12_models import Base, SECRET, engine, pwd
from app.v12_helpers import db, parse_date

router = APIRouter()


class LenderAccount(Base):
    __tablename__ = 'lender_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    cpf: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    rg: Mapped[str] = mapped_column(String(30), default='')
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    whatsapp: Mapped[str] = mapped_column(String(30), default='')
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    profession: Mapped[str] = mapped_column(String(120), default='')
    address: Mapped[str] = mapped_column(String(255), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    state: Mapped[str] = mapped_column(String(40), default='')
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LenderClient(Base):
    __tablename__ = 'lender_clients'
    id: Mapped[int] = mapped_column(primary_key=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey('lender_accounts.id'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    cpf: Mapped[str] = mapped_column(String(20), default='', index=True)
    whatsapp: Mapped[str] = mapped_column(String(30), default='')
    phone: Mapped[str] = mapped_column(String(30), default='')
    email: Mapped[str] = mapped_column(String(160), default='')
    address: Mapped[str] = mapped_column(String(255), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    state: Mapped[str] = mapped_column(String(40), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LenderLoan(Base):
    __tablename__ = 'lender_loans'
    id: Mapped[int] = mapped_column(primary_key=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey('lender_accounts.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('lender_clients.id'), index=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(30))
    principal: Mapped[float] = mapped_column(Float)
    rate: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    installments: Mapped[int] = mapped_column(Integer)
    installment_value: Mapped[float] = mapped_column(Float)
    first_due: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LenderInstallment(Base):
    __tablename__ = 'lender_installments'
    id: Mapped[int] = mapped_column(primary_key=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey('lender_accounts.id'), index=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey('lender_loans.id'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    paid_amount: Mapped[float] = mapped_column(Float, default=0)
    paid_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class LenderPayment(Base):
    __tablename__ = 'lender_payments'
    id: Mapped[int] = mapped_column(primary_key=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey('lender_accounts.id'), index=True)
    installment_id: Mapped[int] = mapped_column(ForeignKey('lender_installments.id'), index=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey('lender_loans.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('lender_clients.id'), index=True)
    amount: Mapped[float] = mapped_column(Float)
    payment_date: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(30), default='PIX')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)


def digits(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def make_lender_token(account: LenderAccount) -> str:
    return jwt.encode(
        {
            'sub': str(account.id),
            'scope': 'lender',
            'exp': datetime.utcnow() + timedelta(hours=24),
        },
        SECRET,
        algorithm='HS256',
    )


def current_lender(authorization: Optional[str], s: Session) -> LenderAccount:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Não autenticado')
    try:
        payload = jwt.decode(authorization[7:], SECRET, algorithms=['HS256'])
        if payload.get('scope') != 'lender':
            raise ValueError('scope')
        account = s.get(LenderAccount, int(payload['sub']))
    except Exception:
        raise HTTPException(401, 'Token inválido ou expirado')
    if not account or not account.active:
        raise HTTPException(401, 'Conta inativa')
    return account


def account_dict(x: LenderAccount):
    return {
        'id': x.id,
        'name': x.name,
        'cpf': x.cpf,
        'rg': x.rg,
        'birth_date': str(x.birth_date) if x.birth_date else '',
        'whatsapp': x.whatsapp,
        'email': x.email,
        'profession': x.profession,
        'address': x.address,
        'city': x.city,
        'state': x.state,
        'created_at': x.created_at.isoformat() if x.created_at else '',
    }


def client_dict(x: LenderClient):
    return {
        'id': x.id,
        'name': x.name,
        'cpf': x.cpf,
        'whatsapp': x.whatsapp,
        'phone': x.phone,
        'email': x.email,
        'address': x.address,
        'city': x.city,
        'state': x.state,
        'notes': x.notes,
        'created_at': x.created_at.isoformat() if x.created_at else '',
    }


def require_client(s: Session, lender_id: int, client_id: int) -> LenderClient:
    x = s.query(LenderClient).filter_by(id=client_id, lender_id=lender_id).first()
    if not x:
        raise HTTPException(404, 'Cliente não encontrado')
    return x


def require_loan(s: Session, lender_id: int, loan_id: int) -> LenderLoan:
    x = s.query(LenderLoan).filter_by(id=loan_id, lender_id=lender_id).first()
    if not x:
        raise HTTPException(404, 'Empréstimo não encontrado')
    return x


def require_installment(s: Session, lender_id: int, installment_id: int) -> LenderInstallment:
    x = s.query(LenderInstallment).filter_by(id=installment_id, lender_id=lender_id).first()
    if not x:
        raise HTTPException(404, 'Parcela não encontrada')
    return x


def daily_dates(first_due: date, count: int = 20):
    dates = []
    current = first_due
    while len(dates) < count:
        if current.weekday() != 6:
            dates.append(current)
        current += timedelta(days=1)
    return dates


@router.post('/api/lender/register')
def lender_register(
    name: str = Form(...),
    cpf: str = Form(...),
    rg: str = Form(''),
    birth_date: str = Form(''),
    whatsapp: str = Form(...),
    email: str = Form(...),
    profession: str = Form(''),
    address: str = Form(''),
    city: str = Form(''),
    state: str = Form(''),
    password: str = Form(...),
    consent: str = Form(...),
    s: Session = Depends(db),
):
    name = name.strip()
    cpf_value = digits(cpf)
    email_value = email.strip().lower()
    whatsapp_value = digits(whatsapp)
    if len(name) < 3:
        raise HTTPException(400, 'Informe o nome completo.')
    if len(cpf_value) != 11:
        raise HTTPException(400, 'CPF deve conter 11 números.')
    if '@' not in email_value or '.' not in email_value.rsplit('@', 1)[-1]:
        raise HTTPException(400, 'Informe um e-mail válido.')
    if len(whatsapp_value) < 10:
        raise HTTPException(400, 'Informe um WhatsApp válido com DDD.')
    if len(password) < 8:
        raise HTTPException(400, 'A senha deve ter pelo menos 8 caracteres.')
    if consent.lower() not in ('1', 'true', 'on', 'sim'):
        raise HTTPException(400, 'É necessário aceitar os termos de cadastro.')
    if s.query(LenderAccount).filter_by(cpf=cpf_value).first():
        raise HTTPException(409, 'Já existe uma conta com este CPF.')
    if s.query(LenderAccount).filter_by(email=email_value).first():
        raise HTTPException(409, 'Já existe uma conta com este e-mail.')

    account = LenderAccount(
        name=name,
        cpf=cpf_value,
        rg=rg.strip(),
        birth_date=parse_date(birth_date, 'data de nascimento', optional=True),
        whatsapp=whatsapp.strip(),
        email=email_value,
        profession=profession.strip(),
        address=address.strip(),
        city=city.strip(),
        state=state.strip(),
        password_hash=pwd.hash(password),
        active=True,
    )
    s.add(account)
    s.commit()
    s.refresh(account)
    return {'ok': True, 'token': make_lender_token(account), 'account': account_dict(account)}


@router.post('/api/lender/login')
def lender_login(email: str = Form(...), password: str = Form(...), s: Session = Depends(db)):
    account = s.query(LenderAccount).filter_by(email=email.strip().lower()).first()
    if not account or not account.active or not pwd.verify(password, account.password_hash):
        raise HTTPException(401, 'E-mail ou senha inválidos')
    return {'token': make_lender_token(account), 'account': account_dict(account)}


@router.get('/api/lender/me')
def lender_me(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    return account_dict(current_lender(authorization, s))


@router.patch('/api/lender/me')
def lender_update_profile(
    name: str = Form(...), whatsapp: str = Form(''), profession: str = Form(''),
    address: str = Form(''), city: str = Form(''), state: str = Form(''),
    authorization: Optional[str] = Header(None), s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    if len(name.strip()) < 3:
        raise HTTPException(400, 'Informe o nome completo.')
    account.name = name.strip()
    account.whatsapp = whatsapp.strip()
    account.profession = profession.strip()
    account.address = address.strip()
    account.city = city.strip()
    account.state = state.strip()
    s.commit()
    return {'ok': True, 'account': account_dict(account)}


@router.get('/api/lender/dashboard')
def lender_dashboard(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    account = current_lender(authorization, s)
    today_ = date.today()
    installments = s.query(LenderInstallment).filter_by(lender_id=account.id).all()
    pending = [i for i in installments if i.status != 'paid']
    overdue = [i for i in pending if i.due_date < today_]
    payments = s.query(LenderPayment).filter_by(lender_id=account.id).all()
    month_start = today_.replace(day=1)
    loans = s.query(LenderLoan).filter_by(lender_id=account.id).all()
    return {
        'clients': s.query(LenderClient).filter_by(lender_id=account.id).count(),
        'loans': len(loans),
        'active_loans': sum(1 for x in loans if x.status == 'active'),
        'principal_total': round(sum(x.principal for x in loans), 2),
        'receivable': round(sum(max(0, i.amount - i.paid_amount) for i in pending), 2),
        'overdue': round(sum(max(0, i.amount - i.paid_amount) for i in overdue), 2),
        'overdue_count': len(overdue),
        'due_today': round(sum(max(0, i.amount - i.paid_amount) for i in pending if i.due_date == today_), 2),
        'received_today': round(sum(p.amount for p in payments if p.payment_date == today_), 2),
        'received_month': round(sum(p.amount for p in payments if month_start <= p.payment_date <= today_), 2),
    }


@router.get('/api/lender/clients')
def lender_clients(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    account = current_lender(authorization, s)
    return [client_dict(x) for x in s.query(LenderClient).filter_by(lender_id=account.id).order_by(LenderClient.name).all()]


@router.post('/api/lender/clients')
def lender_create_client(
    name: str = Form(...), cpf: str = Form(''), whatsapp: str = Form(''), phone: str = Form(''),
    email: str = Form(''), address: str = Form(''), city: str = Form(''), state: str = Form(''),
    notes: str = Form(''), authorization: Optional[str] = Header(None), s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    if len(name.strip()) < 2:
        raise HTTPException(400, 'Informe o nome do cliente.')
    cpf_value = digits(cpf)
    if cpf_value and len(cpf_value) != 11:
        raise HTTPException(400, 'CPF deve conter 11 números.')
    if cpf_value and s.query(LenderClient).filter_by(lender_id=account.id, cpf=cpf_value).first():
        raise HTTPException(409, 'Este CPF já está na sua carteira.')
    x = LenderClient(
        lender_id=account.id, name=name.strip(), cpf=cpf_value, whatsapp=whatsapp.strip(), phone=phone.strip(),
        email=email.strip().lower(), address=address.strip(), city=city.strip(), state=state.strip(), notes=notes.strip(),
    )
    s.add(x); s.commit(); s.refresh(x)
    return client_dict(x)


@router.patch('/api/lender/clients/{client_id}')
def lender_edit_client(
    client_id: int, name: str = Form(...), cpf: str = Form(''), whatsapp: str = Form(''),
    phone: str = Form(''), email: str = Form(''), address: str = Form(''), city: str = Form(''),
    state: str = Form(''), notes: str = Form(''), authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    x = require_client(s, account.id, client_id)
    cpf_value = digits(cpf)
    if cpf_value and len(cpf_value) != 11:
        raise HTTPException(400, 'CPF deve conter 11 números.')
    duplicate = s.query(LenderClient).filter(
        LenderClient.lender_id == account.id,
        LenderClient.cpf == cpf_value,
        LenderClient.id != x.id,
    ).first() if cpf_value else None
    if duplicate:
        raise HTTPException(409, 'Este CPF já está na sua carteira.')
    x.name = name.strip(); x.cpf = cpf_value; x.whatsapp = whatsapp.strip(); x.phone = phone.strip()
    x.email = email.strip().lower(); x.address = address.strip(); x.city = city.strip(); x.state = state.strip(); x.notes = notes.strip()
    s.commit()
    return client_dict(x)


@router.get('/api/lender/loans')
def lender_loans(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    account = current_lender(authorization, s)
    rows = []
    for x in s.query(LenderLoan).filter_by(lender_id=account.id).order_by(LenderLoan.id.desc()).all():
        client = require_client(s, account.id, x.client_id)
        rows.append({
            'id': x.id, 'number': x.number, 'client_id': x.client_id, 'client': client.name,
            'kind': x.kind, 'principal': x.principal, 'rate': x.rate, 'total': x.total,
            'installments': x.installments, 'installment_value': x.installment_value,
            'first_due': str(x.first_due), 'status': x.status,
        })
    return rows


@router.post('/api/lender/loans')
def lender_create_loan(
    client_id: int = Form(...), kind: str = Form(...), principal: float = Form(...),
    first_due: str = Form(...), authorization: Optional[str] = Header(None), s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    client = require_client(s, account.id, client_id)
    if principal <= 0:
        raise HTTPException(400, 'O valor deve ser maior que zero.')
    options = {
        'daily20': {'rate': 20.0, 'installments': 20},
        'final20': {'rate': 30.0, 'installments': 1},
        'final30': {'rate': 35.0, 'installments': 1},
    }
    if kind not in options:
        raise HTTPException(400, 'Modalidade inválida.')
    cfg = options[kind]
    due = parse_date(first_due, 'primeiro vencimento')
    count = cfg['installments']
    total = round(principal * (1 + cfg['rate'] / 100), 2)
    base_cents = int(total * 100) // count
    amounts = [base_cents / 100 for _ in range(count)]
    amounts[-1] = round(total - sum(amounts[:-1]), 2)
    dates = daily_dates(due, 20) if kind == 'daily20' else [due]
    number = f'EMP-{account.id}-{datetime.now().strftime("%y%m%d%H%M%S%f")[-12:]}'
    loan = LenderLoan(
        lender_id=account.id, client_id=client.id, number=number, kind=kind, principal=principal,
        rate=cfg['rate'], total=total, installments=count, installment_value=round(total / count, 2),
        first_due=dates[0], status='active',
    )
    s.add(loan); s.flush()
    for idx, (due_date, amount) in enumerate(zip(dates, amounts), 1):
        s.add(LenderInstallment(
            lender_id=account.id, loan_id=loan.id, number=idx, due_date=due_date,
            amount=amount, status='pending', paid_amount=0,
        ))
    s.commit(); s.refresh(loan)
    return {'id': loan.id, 'number': loan.number, 'total': loan.total}


@router.get('/api/lender/loans/{loan_id}')
def lender_loan_detail(loan_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    account = current_lender(authorization, s)
    loan = require_loan(s, account.id, loan_id)
    client = require_client(s, account.id, loan.client_id)
    items = s.query(LenderInstallment).filter_by(lender_id=account.id, loan_id=loan.id).order_by(LenderInstallment.number).all()
    return {
        'id': loan.id, 'number': loan.number, 'client': client.name, 'client_id': client.id,
        'kind': loan.kind, 'principal': loan.principal, 'rate': loan.rate, 'total': loan.total,
        'installments': loan.installments, 'installment_value': loan.installment_value,
        'first_due': str(loan.first_due), 'status': loan.status,
        'items': [
            {'id': i.id, 'number': i.number, 'due_date': str(i.due_date), 'amount': i.amount,
             'status': i.status, 'paid_amount': i.paid_amount, 'paid_at': str(i.paid_at) if i.paid_at else ''}
            for i in items
        ],
    }


@router.get('/api/lender/installments')
def lender_installments(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    account = current_lender(authorization, s)
    rows = []
    q = s.query(LenderInstallment).filter_by(lender_id=account.id).order_by(LenderInstallment.due_date, LenderInstallment.number)
    for i in q.all():
        loan = require_loan(s, account.id, i.loan_id)
        client = require_client(s, account.id, loan.client_id)
        rows.append({
            'id': i.id, 'loan_id': loan.id, 'loan': loan.number, 'client_id': client.id, 'client': client.name,
            'number': i.number, 'due_date': str(i.due_date), 'amount': i.amount, 'status': i.status,
            'paid_amount': i.paid_amount, 'paid_at': str(i.paid_at) if i.paid_at else '', 'whatsapp': client.whatsapp,
        })
    return rows


@router.post('/api/lender/installments/{installment_id}/mark-paid')
def lender_mark_paid(
    installment_id: int, payment_date: str = Form(''), method: str = Form('PIX'),
    authorization: Optional[str] = Header(None), s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    item = require_installment(s, account.id, installment_id)
    if item.status == 'paid':
        return {'ok': True, 'already_paid': True}
    loan = require_loan(s, account.id, item.loan_id)
    paid = parse_date(payment_date, 'data do pagamento', optional=True) or date.today()
    remaining = round(max(0, item.amount - item.paid_amount), 2)
    payment = LenderPayment(
        lender_id=account.id, installment_id=item.id, loan_id=loan.id, client_id=loan.client_id,
        amount=remaining, payment_date=paid, method=(method or 'PIX')[:30],
    )
    item.paid_amount = item.amount; item.paid_at = paid; item.status = 'paid'
    s.add(payment); s.commit(); s.refresh(payment)
    open_items = s.query(LenderInstallment).filter(
        LenderInstallment.lender_id == account.id,
        LenderInstallment.loan_id == loan.id,
        LenderInstallment.status != 'paid',
    ).count()
    if open_items == 0:
        loan.status = 'paid'; s.commit()
    return {'ok': True, 'payment_id': payment.id}


@router.post('/api/lender/installments/{installment_id}/mark-unpaid')
def lender_mark_unpaid(
    installment_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    item = require_installment(s, account.id, installment_id)
    loan = require_loan(s, account.id, item.loan_id)
    for payment in s.query(LenderPayment).filter_by(lender_id=account.id, installment_id=item.id).all():
        s.delete(payment)
    item.paid_amount = 0; item.paid_at = None; item.status = 'pending'; loan.status = 'active'
    s.commit()
    return {'ok': True}


@router.get('/api/lender/payments')
def lender_payments(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    account = current_lender(authorization, s)
    rows = []
    for p in s.query(LenderPayment).filter_by(lender_id=account.id).order_by(LenderPayment.id.desc()).limit(500).all():
        client = require_client(s, account.id, p.client_id)
        rows.append({
            'id': p.id, 'client': client.name, 'client_id': client.id, 'amount': p.amount,
            'payment_date': str(p.payment_date), 'method': p.method, 'loan_id': p.loan_id,
        })
    return rows
