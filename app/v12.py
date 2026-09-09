from datetime import datetime, timedelta, date
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Form, Header, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.v12_models import (
    SessionLocal, pwd, ADMIN_USER, ADMIN_PASS, User, Client, Product, Contract, Installment,
    Payment, Cash, Closing, ClientAttachment
)
from app.v12_helpers import (
    db, parse_date, make_token, current_user, require_admin, log, client_to_dict,
    visible_contracts_query, make_receipt_pdf
)

app = FastAPI(title='CRED+ Financeira API', version='12.0.0')
app.mount('/static', StaticFiles(directory='app/static'), name='static')


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    print('UNEXPECTED ERROR', repr(exc))
    return JSONResponse(status_code=500, content={'detail': 'Erro interno do servidor. A operação não foi concluída.'})


@app.on_event('startup')
def seed():
    s = SessionLocal()
    try:
        if not s.query(User).filter_by(username=ADMIN_USER).first():
            s.add(User(name='Administrador', username=ADMIN_USER, password_hash=pwd.hash(ADMIN_PASS), role='admin'))
        if s.query(Product).count() == 0:
            s.add_all([
                Product(name='Diário • 20 parcelas', rate=20, days=20, periodicity='daily'),
                Product(name='Final • 20 dias', rate=30, days=20, periodicity='final'),
                Product(name='Final • 30 dias', rate=35, days=30, periodicity='final'),
            ])
        s.commit()
    finally:
        s.close()


@app.get('/health')
def health():
    return {'ok': True, 'version': '12.0.0'}


@app.get('/')
def home():
    return FileResponse('app/static/v12.html')


@app.post('/api/login')
def login(username: str = Form(...), password: str = Form(...), s: Session = Depends(db)):
    u = s.query(User).filter_by(username=username).first()
    if not u or not u.active or not pwd.verify(password, u.password_hash):
        raise HTTPException(401, 'Usuário ou senha inválidos')
    log(s, u, 'LOGIN', 'Acesso realizado')
    return {'token': make_token(u), 'user': {'id': u.id, 'name': u.name, 'role': u.role}}


@app.get('/api/me')
def me(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    return {'id': u.id, 'name': u.name, 'role': u.role}


@app.get('/api/dashboard')
def dashboard(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    today_ = date.today()
    iq = s.query(Installment).join(Contract)
    if u.role == 'collector':
        iq = iq.filter(Contract.collector_id == u.id)
    installments = iq.all()
    receivable = sum(max(0, i.amount - i.paid_amount) for i in installments if i.status != 'paid')
    overdue = sum(max(0, i.amount - i.paid_amount) for i in installments if i.status != 'paid' and i.due_date < today_)
    pq = s.query(Payment)
    if u.role == 'collector':
        pq = pq.filter(Payment.collector_id == u.id)
    received_today = sum(p.amount for p in pq.filter(Payment.payment_date == today_).all())
    cash_in = sum(x.amount for x in s.query(Cash).filter(Cash.kind == 'in').all())
    cash_out = sum(x.amount for x in s.query(Cash).filter(Cash.kind == 'out').all())
    cq = s.query(Client)
    if u.role == 'collector':
        cq = cq.filter(Client.collector_id == u.id)
    kq = visible_contracts_query(s, u).filter(Contract.status == 'active')
    overdue_count = sum(1 for i in installments if i.status != 'paid' and i.due_date < today_)
    return {
        'cash': cash_in - cash_out,
        'receivable': receivable,
        'overdue': overdue,
        'received_today': received_today,
        'clients': cq.count(),
        'contracts': kq.count(),
        'installments_total': len(installments),
        'installments_paid': sum(1 for i in installments if i.status == 'paid'),
        'installments_overdue': overdue_count,
        'role': u.role,
    }


@app.get('/api/clients')
def clients(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    q = s.query(Client)
    if u.role == 'collector':
        q = q.filter(Client.collector_id == u.id)
    return [client_to_dict(x, s) for x in q.order_by(Client.name).all()]


@app.get('/api/clients/{client_id}')
def client_detail(client_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    x = s.get(Client, client_id)
    if not x:
        raise HTTPException(404, 'Cliente não encontrado')
    if u.role == 'collector' and x.collector_id != u.id:
        raise HTTPException(403, 'Cliente fora da sua carteira')
    data = client_to_dict(x, s)
    data['attachments'] = [
        {'id': a.id, 'category': a.category, 'filename': a.filename, 'content_type': a.content_type, 'size': a.size}
        for a in s.query(ClientAttachment).filter_by(client_id=x.id).order_by(ClientAttachment.id.desc()).all()
    ]
    data['contracts'] = [
        {'id': c.id, 'number': c.number, 'principal': c.principal, 'total': c.total, 'installments': c.installments, 'status': c.status}
        for c in s.query(Contract).filter_by(client_id=x.id).order_by(Contract.id.desc()).all()
    ]
    return data


def client_form_payload(
    name, cpf, rg, birth_date, whatsapp, phone, email, marital_status, profession,
    company, time_at_work, income, address, cep, street, address_number, neighborhood,
    city, state, address_reference, reference1_name, reference1_phone, reference2_name,
    reference2_phone, notes, collector_id
):
    return dict(
        name=name, cpf=cpf, rg=rg, birth_date=parse_date(birth_date, 'data de nascimento', optional=True),
        whatsapp=whatsapp, phone=phone, email=email, marital_status=marital_status,
        profession=profession, company=company, time_at_work=time_at_work, income=income,
        address=address, cep=cep, street=street, address_number=address_number,
        neighborhood=neighborhood, city=city, state=state, address_reference=address_reference,
        reference1_name=reference1_name, reference1_phone=reference1_phone,
        reference2_name=reference2_name, reference2_phone=reference2_phone,
        notes=notes, collector_id=collector_id,
    )


@app.post('/api/clients')
def create_client(
    name: str = Form(...), cpf: str = Form(''), rg: str = Form(''), birth_date: str = Form(''),
    whatsapp: str = Form(''), phone: str = Form(''), email: str = Form(''), marital_status: str = Form(''),
    profession: str = Form(''), company: str = Form(''), time_at_work: str = Form(''), income: float = Form(0),
    address: str = Form(''), cep: str = Form(''), street: str = Form(''), address_number: str = Form(''),
    neighborhood: str = Form(''), city: str = Form(''), state: str = Form(''), address_reference: str = Form(''),
    reference1_name: str = Form(''), reference1_phone: str = Form(''), reference2_name: str = Form(''),
    reference2_phone: str = Form(''), notes: str = Form(''), collector_id: Optional[int] = Form(None),
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    u = current_user(authorization, s)
    cid = collector_id if u.role == 'admin' else u.id
    payload = client_form_payload(name, cpf, rg, birth_date, whatsapp, phone, email, marital_status, profession,
                                  company, time_at_work, income, address, cep, street, address_number,
                                  neighborhood, city, state, address_reference, reference1_name, reference1_phone,
                                  reference2_name, reference2_phone, notes, cid)
    x = Client(**payload)
    s.add(x); s.commit(); s.refresh(x)
    log(s, u, 'CLIENT_CREATE', name)
    return {'id': x.id}


@app.patch('/api/clients/{client_id}')
def update_client(
    client_id: int, name: str = Form(...), cpf: str = Form(''), rg: str = Form(''), birth_date: str = Form(''),
    whatsapp: str = Form(''), phone: str = Form(''), email: str = Form(''), marital_status: str = Form(''),
    profession: str = Form(''), company: str = Form(''), time_at_work: str = Form(''), income: float = Form(0),
    address: str = Form(''), cep: str = Form(''), street: str = Form(''), address_number: str = Form(''),
    neighborhood: str = Form(''), city: str = Form(''), state: str = Form(''), address_reference: str = Form(''),
    reference1_name: str = Form(''), reference1_phone: str = Form(''), reference2_name: str = Form(''),
    reference2_phone: str = Form(''), notes: str = Form(''), collector_id: Optional[int] = Form(None),
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    u = current_user(authorization, s)
    x = s.get(Client, client_id)
    if not x:
        raise HTTPException(404, 'Cliente não encontrado')
    if u.role == 'collector' and x.collector_id != u.id:
        raise HTTPException(403, 'Cliente fora da sua carteira')
    cid = collector_id if u.role == 'admin' else u.id
    payload = client_form_payload(name, cpf, rg, birth_date, whatsapp, phone, email, marital_status, profession,
                                  company, time_at_work, income, address, cep, street, address_number,
                                  neighborhood, city, state, address_reference, reference1_name, reference1_phone,
                                  reference2_name, reference2_phone, notes, cid)
    for k, v in payload.items(): setattr(x, k, v)
    s.commit(); log(s, u, 'CLIENT_EDIT', f'{client_id}:{name}')
    return {'ok': True}


@app.post('/api/clients/{client_id}/attachments')
async def upload_attachment(
    client_id: int, category: str = Form('document'), file: UploadFile = File(...),
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    u = current_user(authorization, s)
    x = s.get(Client, client_id)
    if not x:
        raise HTTPException(404, 'Cliente não encontrado')
    if u.role == 'collector' and x.collector_id != u.id:
        raise HTTPException(403, 'Cliente fora da sua carteira')
    if category not in ('photo', 'document'):
        raise HTTPException(400, 'Categoria inválida')
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, 'Arquivo maior que 5 MB')
    a = ClientAttachment(client_id=client_id, category=category, filename=file.filename or 'arquivo',
                         content_type=file.content_type or 'application/octet-stream', size=len(data), data=data)
    s.add(a); s.commit(); s.refresh(a)
    log(s, u, 'CLIENT_ATTACHMENT', f'{client_id}:{a.filename}')
    return {'id': a.id}


@app.get('/api/attachments/{attachment_id}')
def attachment_file(attachment_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    a = s.get(ClientAttachment, attachment_id)
    if not a:
        raise HTTPException(404, 'Arquivo não encontrado')
    client = s.get(Client, a.client_id)
    if u.role == 'collector' and client and client.collector_id != u.id:
        raise HTTPException(403, 'Arquivo fora da sua carteira')
    return Response(content=a.data, media_type=a.content_type,
                    headers={'Content-Disposition': f'inline; filename="{a.filename}"'})


from app.v12_finance import router as finance_router
from app.v12_admin import router as admin_router
app.include_router(finance_router)
app.include_router(admin_router)
