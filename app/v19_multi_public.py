from datetime import date, datetime
from typing import Optional
import jwt

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.v12_models import Base, SECRET, engine
from app.v12_helpers import db, parse_date
from app.v14_public import MAX_IMAGE_SIZE, calculate_credit_score, valid_image_upload
from app.v15_lender import LenderAccount, LenderClient, current_lender, digits, client_dict

router = APIRouter()


class LenderClientProfile(Base):
    __tablename__ = 'lender_client_profiles'
    id: Mapped[int] = mapped_column(primary_key=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey('lender_accounts.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('lender_clients.id'), unique=True, index=True)
    rg: Mapped[str] = mapped_column(String(30))
    profession: Mapped[str] = mapped_column(String(120))
    company: Mapped[str] = mapped_column(String(160))
    income: Mapped[float] = mapped_column(Float)
    income_payment_date: Mapped[date] = mapped_column(Date)
    time_at_work_months: Mapped[int] = mapped_column(Integer)
    cep: Mapped[str] = mapped_column(String(20))
    street: Mapped[str] = mapped_column(String(180))
    address_number: Mapped[str] = mapped_column(String(30))
    neighborhood: Mapped[str] = mapped_column(String(120))
    address_reference: Mapped[str] = mapped_column(String(220))
    reference1_name: Mapped[str] = mapped_column(String(160))
    reference1_phone: Mapped[str] = mapped_column(String(30))
    reference2_name: Mapped[str] = mapped_column(String(160))
    reference2_phone: Mapped[str] = mapped_column(String(30))
    credit_score: Mapped[int] = mapped_column(Integer)
    score_band: Mapped[str] = mapped_column(String(20))
    suggested_limit: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LenderClientAttachment(Base):
    __tablename__ = 'lender_client_attachments'
    id: Mapped[int] = mapped_column(primary_key=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey('lender_accounts.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('lender_clients.id'), index=True)
    category: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)


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
async def public_lender_client_register(
    token: str,
    name: str = Form(...),
    cpf: str = Form(...),
    rg: str = Form(...),
    whatsapp: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    profession: str = Form(...),
    company: str = Form(...),
    income: float = Form(...),
    income_payment_date: str = Form(...),
    time_at_work_months: int = Form(...),
    cep: str = Form(...),
    street: str = Form(...),
    address_number: str = Form(...),
    neighborhood: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    address_reference: str = Form(...),
    reference1_name: str = Form(...),
    reference1_phone: str = Form(...),
    reference2_name: str = Form(...),
    reference2_phone: str = Form(...),
    notes: str = Form(''),
    consent: str = Form(...),
    selfie: UploadFile = File(...),
    residence_proof: UploadFile = File(...),
    s: Session = Depends(db),
):
    account = account_from_public_token(token, s)

    name = name.strip()
    cpf_value = digits(cpf)
    rg_value = rg.strip()
    whatsapp_value = digits(whatsapp)
    phone_value = digits(phone)
    email_value = email.strip().lower()

    required_texts = {
        'nome completo': name,
        'RG': rg_value,
        'WhatsApp': whatsapp.strip(),
        'telefone': phone.strip(),
        'e-mail': email_value,
        'profissão': profession.strip(),
        'empresa / trabalho': company.strip(),
        'CEP': cep.strip(),
        'rua': street.strip(),
        'número': address_number.strip(),
        'bairro': neighborhood.strip(),
        'cidade': city.strip(),
        'estado': state.strip(),
        'ponto de referência / complemento': address_reference.strip(),
        'referência 1 - nome': reference1_name.strip(),
        'referência 1 - telefone': reference1_phone.strip(),
        'referência 2 - nome': reference2_name.strip(),
        'referência 2 - telefone': reference2_phone.strip(),
    }
    missing = [label for label, value in required_texts.items() if not value]
    if missing:
        raise HTTPException(400, 'Preencha todos os campos obrigatórios: ' + ', '.join(missing) + '.')

    if len(name) < 3:
        raise HTTPException(400, 'Informe seu nome completo.')
    if len(cpf_value) != 11:
        raise HTTPException(400, 'CPF deve conter 11 números.')
    if len(rg_value) < 3:
        raise HTTPException(400, 'Informe um RG válido.')
    if len(whatsapp_value) < 10:
        raise HTTPException(400, 'Informe um WhatsApp válido com DDD.')
    if len(phone_value) < 10:
        raise HTTPException(400, 'Informe um telefone válido com DDD.')
    if '@' not in email_value or '.' not in email_value.rsplit('@', 1)[-1]:
        raise HTTPException(400, 'Informe um e-mail válido.')
    if income <= 0:
        raise HTTPException(400, 'Informe sua renda mensal declarada.')
    if time_at_work_months < 0:
        raise HTTPException(400, 'O tempo de trabalho não pode ser negativo.')
    if len(digits(reference1_phone)) < 10 or len(digits(reference2_phone)) < 10:
        raise HTTPException(400, 'Informe telefones válidos para as duas referências.')
    if consent.lower() not in ('1', 'true', 'on', 'sim'):
        raise HTTPException(400, 'É necessário autorizar o envio do cadastro.')

    payment_date = parse_date(income_payment_date, 'data do pagamento')

    existing = s.query(LenderClient).filter_by(lender_id=account.id, cpf=cpf_value).first()
    if existing:
        raise HTTPException(409, 'Este CPF já possui cadastro nesta carteira.')

    if not valid_image_upload(selfie):
        raise HTTPException(400, 'A selfie precisa ser uma foto válida (JPG, PNG, WEBP, HEIC ou HEIF).')
    selfie_data = await selfie.read()
    if not selfie_data:
        raise HTTPException(400, 'Envie uma selfie.')
    if len(selfie_data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, 'A selfie deve ter no máximo 5 MB.')

    if not valid_image_upload(residence_proof):
        raise HTTPException(400, 'O comprovante de residência precisa ser uma foto válida (JPG, PNG, WEBP, HEIC ou HEIF).')
    proof_data = await residence_proof.read()
    if not proof_data:
        raise HTTPException(400, 'Envie a foto do comprovante de residência.')
    if len(proof_data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, 'O comprovante de residência deve ter no máximo 5 MB.')

    score_points, score_band, suggested_limit = calculate_credit_score(
        income=income,
        time_at_work_months=time_at_work_months,
        profession=profession,
        company=company,
        cep=cep,
        street=street,
        address_number=address_number,
        neighborhood=neighborhood,
        city=city,
        state=state,
        address_reference=address_reference,
        reference1_name=reference1_name,
        reference1_phone=reference1_phone,
        reference2_name=reference2_name,
        reference2_phone=reference2_phone,
    )

    full_address = f'{street.strip()}, {address_number.strip()} - {neighborhood.strip()}'
    notes_text = (
        f'Cadastro realizado pelo link público. Pré-score: {score_points}/100, '
        f'faixa {score_band}, limite indicativo R$ {suggested_limit:.2f}. '
        f'Renda declarada R$ {income:.2f}. Recebimento: {payment_date.strftime("%d/%m/%Y")}. '
        f'Tempo no trabalho: {time_at_work_months} meses. Aprovação final manual.'
    )
    if notes.strip():
        notes_text += ' ' + notes.strip()

    client = LenderClient(
        lender_id=account.id,
        name=name,
        cpf=cpf_value,
        whatsapp=whatsapp.strip(),
        phone=phone.strip(),
        email=email_value,
        address=full_address,
        city=city.strip(),
        state=state.strip().upper()[:2],
        notes=notes_text,
    )

    try:
        s.add(client)
        s.flush()

        profile = LenderClientProfile(
            lender_id=account.id,
            client_id=client.id,
            rg=rg_value,
            profession=profession.strip(),
            company=company.strip(),
            income=float(income),
            income_payment_date=payment_date,
            time_at_work_months=int(time_at_work_months),
            cep=cep.strip(),
            street=street.strip(),
            address_number=address_number.strip(),
            neighborhood=neighborhood.strip(),
            address_reference=address_reference.strip(),
            reference1_name=reference1_name.strip(),
            reference1_phone=reference1_phone.strip(),
            reference2_name=reference2_name.strip(),
            reference2_phone=reference2_phone.strip(),
            credit_score=score_points,
            score_band=score_band,
            suggested_limit=suggested_limit,
        )
        s.add(profile)

        s.add(LenderClientAttachment(
            lender_id=account.id,
            client_id=client.id,
            category='selfie',
            filename=(selfie.filename or f'selfie-{client.id}.jpg')[:255],
            content_type=(selfie.content_type or 'application/octet-stream')[:120],
            size=len(selfie_data),
            data=selfie_data,
        ))
        s.add(LenderClientAttachment(
            lender_id=account.id,
            client_id=client.id,
            category='residence_proof',
            filename=(residence_proof.filename or f'comprovante-{client.id}.jpg')[:255],
            content_type=(residence_proof.content_type or 'application/octet-stream')[:120],
            size=len(proof_data),
            data=proof_data,
        ))
        s.commit()
        s.refresh(client)
    except Exception:
        s.rollback()
        raise

    return {
        'ok': True,
        'client': client_dict(client),
        'account_name': account.name,
        'pre_analysis': {
            'score': score_points,
            'band': score_band,
            'suggested_limit': suggested_limit,
            'final_approval_required': True,
        },
    }
