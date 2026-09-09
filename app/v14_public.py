from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app.v12_models import Client
from app.v12_helpers import db, parse_date

router = APIRouter()


def digits(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


@router.post('/api/public/clients')
def public_client_create(
    name: str = Form(...),
    cpf: str = Form(''),
    rg: str = Form(''),
    birth_date: str = Form(''),
    whatsapp: str = Form(''),
    phone: str = Form(''),
    email: str = Form(''),
    marital_status: str = Form(''),
    profession: str = Form(''),
    company: str = Form(''),
    cep: str = Form(''),
    street: str = Form(''),
    address_number: str = Form(''),
    neighborhood: str = Form(''),
    city: str = Form(''),
    state: str = Form(''),
    address: str = Form(''),
    address_reference: str = Form(''),
    notes: str = Form(''),
    consent: str = Form(...),
    s: Session = Depends(db),
):
    name = name.strip()
    if len(name) < 3:
        raise HTTPException(400, 'Informe o nome completo.')
    if consent.lower() not in ('1', 'true', 'on', 'sim'):
        raise HTTPException(400, 'É necessário autorizar o envio dos dados.')

    cpf_value = digits(cpf)
    if cpf_value and len(cpf_value) != 11:
        raise HTTPException(400, 'CPF deve conter 11 números.')
    if cpf_value:
        for existing in s.query(Client).filter(Client.cpf.isnot(None)).all():
            if digits(existing.cpf) == cpf_value:
                raise HTTPException(409, 'Já existe um cadastro com este CPF.')

    client = Client(
        name=name,
        cpf=cpf_value,
        rg=rg.strip(),
        birth_date=parse_date(birth_date, 'data de nascimento', optional=True),
        whatsapp=whatsapp.strip(),
        phone=phone.strip(),
        email=email.strip(),
        marital_status=marital_status.strip(),
        profession=profession.strip(),
        company=company.strip(),
        time_at_work='',
        income=0,
        address=address.strip(),
        cep=cep.strip(),
        street=street.strip(),
        address_number=address_number.strip(),
        neighborhood=neighborhood.strip(),
        city=city.strip(),
        state=state.strip(),
        address_reference=address_reference.strip(),
        reference1_name='',
        reference1_phone='',
        reference2_name='',
        reference2_phone='',
        notes=('Cadastro realizado pelo link público. ' + notes.strip()).strip(),
        collector_id=None,
    )
    s.add(client)
    s.commit()
    s.refresh(client)
    return {'ok': True, 'id': client.id, 'message': 'Cadastro enviado com sucesso.'}
