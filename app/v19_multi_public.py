from typing import Optional
import jwt
from fastapi import APIRouter, Depends, Form, Header, HTTPException
from sqlalchemy.orm import Session

from app.v12_models import SECRET
from app.v12_helpers import db
from app.v15_lender import LenderAccount, LenderClient, current_lender, digits, client_dict

router = APIRouter()


def public_token(account_id: int) -> str:
    return jwt.encode(
        {'scope': 'lender_public_client', 'lender_id': int(account_id)},
        SECRET,
        algorithm='HS256',
    )


def account_from_public_token(token: str, s: Session) -> LenderAccount:
    try:
        payload = jwt.decode(token, SECRET, algorithms=['HS256'])
        if payload.get('scope') != 'lender_public_client':
            raise ValueError('scope')
        account = s.get(LenderAccount, int(payload['lender_id']))
    except Exception:
        raise HTTPException(404, 'Link de cadastro inválido.')
    if not account or not account.active:
        raise HTTPException(404, 'Link de cadastro indisponível.')
    return account


@router.get('/api/lender/public-client-link')
def lender_public_client_link(
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    token = public_token(account.id)
    return {
        'token': token,
        'path': f'/painel/cliente/{token}',
        'account_name': account.name,
    }


@router.get('/api/public/lender-client/{token}')
def public_lender_info(token: str, s: Session = Depends(db)):
    account = account_from_public_token(token, s)
    return {
        'name': account.name,
        'city': account.city or '',
        'state': account.state or '',
    }


@router.post('/api/public/lender-client/{token}')
def public_lender_client_register(
    token: str,
    name: str = Form(...),
    cpf: str = Form(''),
    whatsapp: str = Form(...),
    phone: str = Form(''),
    email: str = Form(''),
    address: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    notes: str = Form(''),
    consent: str = Form(...),
    s: Session = Depends(db),
):
    account = account_from_public_token(token, s)
    name = name.strip()
    cpf_value = digits(cpf)
    whatsapp_value = digits(whatsapp)

    if len(name) < 3:
        raise HTTPException(400, 'Informe seu nome completo.')
    if cpf_value and len(cpf_value) != 11:
        raise HTTPException(400, 'CPF deve conter 11 números.')
    if len(whatsapp_value) < 10:
        raise HTTPException(400, 'Informe um WhatsApp válido com DDD.')
    if len(address.strip()) < 5:
        raise HTTPException(400, 'Informe seu endereço.')
    if len(city.strip()) < 2 or len(state.strip()) < 2:
        raise HTTPException(400, 'Informe cidade e estado.')
    if consent.lower() not in ('1', 'true', 'on', 'sim'):
        raise HTTPException(400, 'É necessário autorizar o envio do cadastro.')

    if cpf_value:
        existing = s.query(LenderClient).filter_by(lender_id=account.id, cpf=cpf_value).first()
        if existing:
            raise HTTPException(409, 'Este CPF já possui cadastro nesta carteira.')

    client = LenderClient(
        lender_id=account.id,
        name=name,
        cpf=cpf_value,
        whatsapp=whatsapp.strip(),
        phone=phone.strip(),
        email=email.strip().lower(),
        address=address.strip(),
        city=city.strip(),
        state=state.strip().upper()[:2],
        notes=('Cadastro realizado pelo link público. ' + notes.strip()).strip(),
    )
    s.add(client)
    s.commit()
    s.refresh(client)
    return {'ok': True, 'client': client_dict(client), 'account_name': account.name}
