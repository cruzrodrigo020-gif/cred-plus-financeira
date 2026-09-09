from io import BytesIO
from datetime import datetime, timedelta, date
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.v12_models import (
    SessionLocal, SECRET, User, Client, Contract, Installment, Payment, Cash,
    ClientAttachment, Audit
)

def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def parse_date(value: str, field_name: str = 'data', optional: bool = False):
    value = (value or '').strip()
    if not value and optional:
        return None
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise HTTPException(400, f'{field_name.capitalize()} inválida. Use DD-MM-AAAA, DD/MM/AAAA ou AAAA-MM-DD.')


def make_token(u):
    return jwt.encode({'sub': str(u.id), 'role': u.role, 'exp': datetime.utcnow() + timedelta(hours=10)}, SECRET, algorithm='HS256')


def current_user(h: Optional[str], s: Session):
    if not h or not h.startswith('Bearer '):
        raise HTTPException(401, 'Não autenticado')
    try:
        p = jwt.decode(h[7:], SECRET, algorithms=['HS256'])
        u = s.get(User, int(p['sub']))
    except Exception:
        raise HTTPException(401, 'Token inválido ou expirado')
    if not u or not u.active:
        raise HTTPException(401, 'Usuário inativo')
    return u


def require_admin(u):
    if u.role != 'admin':
        raise HTTPException(403, 'Acesso restrito ao administrador')


def log(s, u, action, details):
    s.add(Audit(user_id=u.id if u else None, action=action, details=details))
    s.commit()


def client_to_dict(x: Client, s: Optional[Session] = None):
    photo_id = None
    if s is not None:
        photo = s.query(ClientAttachment).filter_by(client_id=x.id, category='photo').order_by(ClientAttachment.id.desc()).first()
        photo_id = photo.id if photo else None
    return {
        'id': x.id, 'name': x.name, 'cpf': x.cpf, 'rg': x.rg,
        'birth_date': str(x.birth_date) if x.birth_date else '',
        'whatsapp': x.whatsapp, 'phone': x.phone, 'email': x.email,
        'marital_status': x.marital_status, 'profession': x.profession,
        'company': x.company, 'time_at_work': x.time_at_work,
        'income': x.income, 'address': x.address, 'cep': x.cep,
        'street': x.street, 'address_number': x.address_number,
        'neighborhood': x.neighborhood, 'city': x.city, 'state': x.state,
        'address_reference': x.address_reference,
        'reference1_name': x.reference1_name, 'reference1_phone': x.reference1_phone,
        'reference2_name': x.reference2_name, 'reference2_phone': x.reference2_phone,
        'notes': x.notes, 'collector_id': x.collector_id,
        'created_at': x.created_at.isoformat() if x.created_at else '',
        'photo_id': photo_id,
    }


def visible_contracts_query(s: Session, u: User):
    q = s.query(Contract)
    if u.role == 'collector':
        q = q.filter(Contract.collector_id == u.id)
    return q


def make_receipt_pdf(payment: Payment, s: Session):
    client = s.get(Client, payment.client_id)
    contract = s.get(Contract, payment.contract_id)
    installment = s.get(Installment, payment.installment_id)
    collector = s.get(User, payment.collector_id) if payment.collector_id else None
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setTitle(f'Recibo CRED+ {payment.id}')
    c.setFont('Helvetica-Bold', 22)
    c.drawString(48, height - 62, 'CRED+ FINANCEIRA')
    c.setFont('Helvetica', 10)
    c.drawString(48, height - 80, 'Recibo de pagamento')
    c.line(48, height - 95, width - 48, height - 95)
    y = height - 130
    lines = [
        ('Recibo nº', f'RCP-{payment.id:06d}'),
        ('Cliente', client.name if client else '-'),
        ('CPF', client.cpf if client else '-'),
        ('Contrato', contract.number if contract else '-'),
        ('Parcela', str(installment.number) if installment else '-'),
        ('Vencimento', installment.due_date.strftime('%d/%m/%Y') if installment else '-'),
        ('Data do pagamento', payment.payment_date.strftime('%d/%m/%Y')),
        ('Valor recebido', f'R$ {payment.amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')),
        ('Forma de pagamento', payment.method or '-'),
        ('Cobrador', collector.name if collector else 'Administração'),
    ]
    for label, value in lines:
        c.setFont('Helvetica-Bold', 10)
        c.drawString(48, y, f'{label}:')
        c.setFont('Helvetica', 10)
        c.drawString(160, y, value)
        y -= 24
    c.line(48, y - 10, width - 48, y - 10)
    c.setFont('Helvetica', 8)
    c.drawString(48, y - 32, f'Emitido em {datetime.now().strftime("%d/%m/%Y %H:%M")}.')
    c.drawString(48, y - 46, 'Documento gerado automaticamente pelo sistema CRED+ Financeira.')
    c.save()
    buf.seek(0)
    return buf
