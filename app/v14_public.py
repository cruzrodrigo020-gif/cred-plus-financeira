import os
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
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
DEFAULT_COMPANY_WHATSAPP = '5591980459857'


def digits(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def company_whatsapp() -> str:
    return digits(os.getenv('COMPANY_WHATSAPP', DEFAULT_COMPANY_WHATSAPP)) or DEFAULT_COMPANY_WHATSAPP


def company_whatsapp_display() -> str:
    value = company_whatsapp()
    if value.startswith('55') and len(value) == 13:
        return f'+55 ({value[2:4]}) {value[4:9]}-{value[9:]}'
    return '+' + value


def email_confirmation_configured() -> bool:
    return bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM'))


def send_email_confirmation(client_id: int, name: str, email: str) -> None:
    if not email or not email_confirmation_configured():
        return

    host = os.getenv('SMTP_HOST', '').strip()
    port = int(os.getenv('SMTP_PORT', '587'))
    username = os.getenv('SMTP_USERNAME', '').strip()
    password = os.getenv('SMTP_PASSWORD', '')
    sender = os.getenv('SMTP_FROM', '').strip()
    security = os.getenv('SMTP_SECURITY', 'starttls').strip().lower()

    msg = EmailMessage()
    msg['Subject'] = 'Cadastro recebido - CRED+ Financeira'
    msg['From'] = sender
    msg['To'] = email
    msg.set_content(
        f'Olá, {name}!\n\n'
        'Recebemos seu cadastro na CRED+ Financeira com sucesso. '
        'Sua ficha foi registrada e seguirá para conferência da nossa equipe.\n\n'
        'Importante: o envio do cadastro não representa aprovação de crédito.\n\n'
        f'WhatsApp oficial: {company_whatsapp_display()}\n\n'
        'CRED+ Financeira'
    )

    try:
        if security == 'ssl':
            with smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context()) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.ehlo()
                if security == 'starttls':
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)
        print(f'PUBLIC_CONFIRM_EMAIL_OK client_id={client_id}')
    except Exception as exc:
        print(f'PUBLIC_CONFIRM_EMAIL_ERROR client_id={client_id} error={type(exc).__name__}')


def normalize_whatsapp(value: str) -> str:
    phone = digits(value)
    if len(phone) in (10, 11):
        phone = '55' + phone
    return phone


@router.post('/api/public/clients')
async def public_client_create(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    collector_name: str = Form(...),
    cpf: str = Form(...),
    rg: str = Form(...),
    birth_date: str = Form(''),
    whatsapp: str = Form(...),
    phone: str = Form(''),
    email: str = Form(...),
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
    whatsapp_value = whatsapp.strip()
    email_value = email.strip().lower()

    if len(name) < 3:
        raise HTTPException(400, 'Informe o nome completo.')
    if len(collector_name) < 2:
        raise HTTPException(400, 'Informe o nome do cobrador.')
    if not rg_value:
        raise HTTPException(400, 'Informe o RG.')
    if len(normalize_whatsapp(whatsapp_value)) < 12:
        raise HTTPException(400, 'Informe um WhatsApp válido com DDD.')
    if '@' not in email_value or '.' not in email_value.rsplit('@', 1)[-1]:
        raise HTTPException(400, 'Informe um e-mail válido.')
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
        whatsapp=whatsapp_value,
        phone=phone.strip(),
        email=email_value,
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

    background_tasks.add_task(send_email_confirmation, client.id, name, email_value)

    return {
        'ok': True,
        'id': client.id,
        'message': 'Cadastro enviado com sucesso.',
        'company_whatsapp': company_whatsapp(),
        'confirmations': {
            'email_configured': email_confirmation_configured(),
        },
    }
