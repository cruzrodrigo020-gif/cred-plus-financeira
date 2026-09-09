from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.v12_models import Client, ClientAttachment
from app.v12_helpers import db, parse_date

router = APIRouter()

ALLOWED_SELFIE_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/heic',
    'image/heif',
}
MAX_SELFIE_SIZE = 5 * 1024 * 1024


def digits(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


@router.post('/api/public/clients')
async def public_client_create(
    name: str = Form(...),
    collector_name: str = Form(...),
    cpf: str = Form(...),
    rg: str = Form(...),
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
    selfie: UploadFile = File(...),
    s: Session = Depends(db),
):
    name = name.strip()
    collector_name = collector_name.strip()
    rg_value = rg.strip()

    if len(name) < 3:
        raise HTTPException(400, 'Informe o nome completo.')
    if len(collector_name) < 2:
        raise HTTPException(400, 'Informe o nome do cobrador.')
    if not rg_value:
        raise HTTPException(400, 'Informe o RG.')
    if consent.lower() not in ('1', 'true', 'on', 'sim'):
        raise HTTPException(400, 'É necessário autorizar o envio dos dados.')

    cpf_value = digits(cpf)
    if len(cpf_value) != 11:
        raise HTTPException(400, 'CPF deve conter 11 números.')
    for existing in s.query(Client).filter(Client.cpf.isnot(None)).all():
        if digits(existing.cpf) == cpf_value:
            raise HTTPException(409, 'Já existe um cadastro com este CPF.')

    selfie_type = (selfie.content_type or '').lower()
    if selfie_type not in ALLOWED_SELFIE_TYPES:
        raise HTTPException(400, 'A selfie deve ser uma imagem JPG, PNG, WEBP ou HEIC.')
    selfie_data = await selfie.read()
    if not selfie_data:
        raise HTTPException(400, 'Envie uma selfie.')
    if len(selfie_data) > MAX_SELFIE_SIZE:
        raise HTTPException(400, 'A selfie deve ter no máximo 5 MB.')

    client_notes = f'Cadastro realizado pelo link público. Cobrador informado: {collector_name}.'
    if notes.strip():
        client_notes += ' ' + notes.strip()

    client = Client(
        name=name,
        cpf=cpf_value,
        rg=rg_value,
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
        notes=client_notes,
        collector_id=None,
    )

    try:
        s.add(client)
        s.flush()
        attachment = ClientAttachment(
            client_id=client.id,
            category='photo',
            filename=(selfie.filename or f'selfie-{client.id}.jpg')[:255],
            content_type=selfie_type,
            size=len(selfie_data),
            data=selfie_data,
        )
        s.add(attachment)
        s.commit()
        s.refresh(client)
    except Exception:
        s.rollback()
        raise

    return {
        'ok': True,
        'id': client.id,
        'message': 'Cadastro enviado com sucesso.',
    }
