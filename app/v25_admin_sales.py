import calendar
import json
import os
import secrets
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.v12_helpers import current_user, db, parse_date
from app.v12_models import Base, Client, User, engine

router = APIRouter()


class AdminSale(Base):
    __tablename__ = 'admin_sales'

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    item_name: Mapped[str] = mapped_column(String(220))
    item_description: Mapped[str] = mapped_column(Text, default='')
    sale_value: Mapped[float] = mapped_column(Float)
    installments: Mapped[int] = mapped_column(Integer)
    installment_value: Mapped[float] = mapped_column(Float)
    first_due: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default='active')
    share_token: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdminSaleInstallment(Base):
    __tablename__ = 'admin_sale_installments'

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey('admin_sales.id'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    paid_amount: Mapped[float] = mapped_column(Float, default=0)
    paid_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


Base.metadata.create_all(engine)


def require_admin_user(authorization: Optional[str], s: Session) -> User:
    user = current_user(authorization, s)
    if user.role != 'admin':
        raise HTTPException(403, 'Acesso restrito ao administrador')
    return user


def require_sale(s: Session, sale_id: int) -> AdminSale:
    sale = s.get(AdminSale, sale_id)
    if not sale:
        raise HTTPException(404, 'Venda não encontrada')
    return sale


def add_months(value: date, months: int) -> date:
    index = value.month - 1 + months
    year = value.year + index // 12
    month = index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def money_br(value: float) -> str:
    raw = f'{float(value or 0):,.2f}'
    return 'R$ ' + raw.replace(',', 'X').replace('.', ',').replace('X', '.')


def only_digits(value: str) -> str:
    return ''.join(c for c in (value or '') if c.isdigit())


def sale_dict(s: Session, sale: AdminSale):
    client = s.get(Client, sale.client_id)
    paid = s.query(AdminSaleInstallment).filter_by(sale_id=sale.id, status='paid').count()
    return {
        'id': sale.id,
        'number': sale.number,
        'client_id': sale.client_id,
        'client': client.name if client else '-',
        'client_whatsapp': (client.whatsapp or client.phone) if client else '',
        'item_name': sale.item_name,
        'item_description': sale.item_description,
        'sale_value': sale.sale_value,
        'installments': sale.installments,
        'installment_value': sale.installment_value,
        'first_due': str(sale.first_due),
        'status': sale.status,
        'paid_installments': paid,
        'created_at': sale.created_at.isoformat() if sale.created_at else '',
        'contract_path': f'/vendas/contrato/{sale.share_token}.pdf',
    }


def build_contract_pdf(s: Session, sale: AdminSale) -> BytesIO:
    buyer = s.get(Client, sale.client_id)
    seller_user = s.get(User, sale.created_by)
    items = s.query(AdminSaleInstallment).filter_by(sale_id=sale.id).order_by(AdminSaleInstallment.number).all()

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left, right = 48, width - 48
    y = height - 52

    def ensure(space=45):
        nonlocal y
        if y < 70 + space:
            pdf.showPage()
            y = height - 52

    def line(value='', bold=False, size=10, gap=15):
        nonlocal y
        ensure(gap + 5)
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        pdf.drawString(left, y, str(value))
        y -= gap

    def paragraph(value, bold=False, size=10):
        nonlocal y
        for row in textwrap.wrap(str(value), width=92, break_long_words=False, break_on_hyphens=False) or ['']:
            line(row, bold=bold, size=size, gap=14)
        y -= 4

    pdf.setTitle(f'Contrato de Compra e Venda {sale.number}')
    pdf.setFont('Helvetica-Bold', 17)
    pdf.drawCentredString(width / 2, y, 'CONTRATO DE COMPRA E VENDA')
    y -= 22
    pdf.setFont('Helvetica', 9)
    pdf.drawCentredString(width / 2, y, f'CRED+ Financeira • {sale.number}')
    y -= 24
    pdf.line(left, y, right, y)
    y -= 24

    seller_name = seller_user.name if seller_user else 'Administrador'
    buyer_name = buyer.name if buyer else 'Comprador'
    buyer_cpf = buyer.cpf if buyer else ''
    buyer_address = ', '.join(v for v in [
        buyer.address if buyer else '',
        buyer.city if buyer else '',
        buyer.state if buyer else '',
    ] if v) or 'não informado'

    paragraph(f'VENDEDOR(A): CRED+ Financeira, representada neste registro por {seller_name}.', bold=True)
    paragraph(f'COMPRADOR(A): {buyer_name}, CPF {buyer_cpf or "não informado"}, endereço {buyer_address}.', bold=True)

    line('1. OBJETO', bold=True, size=11, gap=17)
    description = f' Descrição: {sale.item_description}.' if sale.item_description else ''
    paragraph(f'O objeto desta compra e venda é: {sale.item_name}.{description}')

    line('2. PREÇO E PAGAMENTO', bold=True, size=11, gap=17)
    paragraph(
        f'O valor total da venda é {money_br(sale.sale_value)}, dividido em {sale.installments} '
        f'parcela(s), conforme cronograma abaixo.'
    )

    line('CRONOGRAMA DE PARCELAS', bold=True, size=10, gap=18)
    pdf.setFont('Helvetica-Bold', 9)
    pdf.drawString(left, y, 'Parcela')
    pdf.drawString(left + 90, y, 'Vencimento')
    pdf.drawString(left + 210, y, 'Valor')
    pdf.drawString(left + 330, y, 'Situação')
    y -= 14
    pdf.line(left, y, right, y)
    y -= 14
    for item in items:
        ensure(24)
        pdf.setFont('Helvetica', 9)
        pdf.drawString(left, y, str(item.number))
        pdf.drawString(left + 90, y, item.due_date.strftime('%d/%m/%Y'))
        pdf.drawString(left + 210, y, money_br(item.amount))
        pdf.drawString(left + 330, y, 'Paga' if item.status == 'paid' else 'Pendente')
        y -= 16
    y -= 8

    line('3. ENTREGA E CONDIÇÕES DO ITEM', bold=True, size=11, gap=17)
    paragraph(
        'O comprador declara ciência das características e condições do item negociado. '
        'Garantias, acessórios e condições adicionais deverão constar da descrição da venda ou de documento complementar.'
    )
    line('4. ATRASO E RENEGOCIAÇÃO', bold=True, size=11, gap=17)
    paragraph(
        'O atraso de parcela deverá ser tratado entre as partes. Multas, juros ou encargos somente serão aplicáveis '
        'quando previamente acordados e permitidos pela legislação.'
    )
    line('5. DISPOSIÇÕES FINAIS', bold=True, size=11, gap=17)
    paragraph(
        'As partes devem conferir os dados deste contrato antes da assinatura. Alterações posteriores deverão ser registradas por escrito.'
    )

    ensure(130)
    y -= 18
    pdf.line(left, y, left + 190, y)
    pdf.line(right - 190, y, right, y)
    y -= 15
    pdf.setFont('Helvetica', 9)
    pdf.drawCentredString(left + 95, y, 'CRED+ Financeira')
    pdf.drawCentredString(right - 95, y, buyer_name[:45])
    y -= 13
    pdf.drawCentredString(left + 95, y, 'VENDEDOR(A)')
    pdf.drawCentredString(right - 95, y, 'COMPRADOR(A)')
    y -= 28
    pdf.setFont('Helvetica', 8)
    pdf.drawString(left, y, f'Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} pelo sistema CRED+ Financeira.')
    y -= 12
    pdf.drawString(left, y, 'Documento automático. Recomenda-se conferência e assinatura das partes.')

    pdf.save()
    buf.seek(0)
    return buf


def public_base(request: Request) -> str:
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()
    return f'https://{domain}' if domain else str(request.base_url).rstrip('/')


def send_whatsapp_document(to_number: str, document_url: str, filename: str, caption: str):
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip()
    phone_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    version = os.getenv('WHATSAPP_GRAPH_VERSION', 'v23.0').strip() or 'v23.0'
    if not token or not phone_id:
        raise HTTPException(503, 'A integração automática do WhatsApp não está configurada.')

    payload = json.dumps({
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': to_number,
        'type': 'document',
        'document': {
            'link': document_url,
            'filename': filename,
            'caption': caption[:1024],
        },
    }).encode('utf-8')
    request = urllib.request.Request(
        f'https://graph.facebook.com/{version}/{phone_id}/messages',
        data=payload,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(raw).get('error', {}).get('message') or raw
        except Exception:
            detail = raw
        raise HTTPException(502, f'WhatsApp não aceitou o envio: {str(detail)[:220]}')
    except Exception as exc:
        raise HTTPException(502, f'Falha ao enviar pelo WhatsApp: {str(exc)[:180]}')


@router.get('/api/sales')
def list_sales(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    require_admin_user(authorization, s)
    return [sale_dict(s, sale) for sale in s.query(AdminSale).order_by(AdminSale.id.desc()).all()]


@router.post('/api/sales')
def create_sale(
    client_id: int = Form(...),
    item_name: str = Form(...),
    item_description: str = Form(''),
    sale_value: float = Form(...),
    installments: int = Form(...),
    first_due: str = Form(...),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    user = require_admin_user(authorization, s)
    client = s.get(Client, client_id)
    if not client:
        raise HTTPException(404, 'Cliente não encontrado')
    if len(item_name.strip()) < 2:
        raise HTTPException(400, 'Informe o item vendido')
    if sale_value <= 0:
        raise HTTPException(400, 'O valor da venda deve ser maior que zero')
    if installments < 1 or installments > 12:
        raise HTTPException(400, 'Escolha entre 1 e 12 parcelas')

    due = parse_date(first_due, 'primeiro vencimento')
    cents = int(round(sale_value * 100))
    base = cents // installments
    amounts = [base / 100 for _ in range(installments)]
    amounts[-1] = round(sale_value - sum(amounts[:-1]), 2)

    sale = AdminSale(
        client_id=client.id,
        created_by=user.id,
        number=f'VEN-{datetime.now().strftime("%y%m%d%H%M%S%f")[-14:]}',
        item_name=item_name.strip(),
        item_description=item_description.strip(),
        sale_value=round(sale_value, 2),
        installments=installments,
        installment_value=round(sale_value / installments, 2),
        first_due=due,
        status='active',
        share_token=secrets.token_urlsafe(32),
    )
    s.add(sale)
    s.flush()
    for index in range(installments):
        s.add(AdminSaleInstallment(
            sale_id=sale.id,
            number=index + 1,
            due_date=add_months(due, index),
            amount=amounts[index],
            status='pending',
            paid_amount=0,
        ))
    s.commit()
    s.refresh(sale)
    return sale_dict(s, sale)


@router.get('/api/sales/{sale_id}')
def sale_detail(sale_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    require_admin_user(authorization, s)
    sale = require_sale(s, sale_id)
    data = sale_dict(s, sale)
    data['items'] = [
        {
            'id': item.id,
            'number': item.number,
            'due_date': str(item.due_date),
            'amount': item.amount,
            'status': item.status,
            'paid_amount': item.paid_amount,
            'paid_at': str(item.paid_at) if item.paid_at else '',
        }
        for item in s.query(AdminSaleInstallment).filter_by(sale_id=sale.id).order_by(AdminSaleInstallment.number).all()
    ]
    return data


@router.post('/api/sales/{sale_id}/installments/{installment_id}/mark-paid')
def mark_sale_paid(
    sale_id: int,
    installment_id: int,
    payment_date: str = Form(''),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    require_admin_user(authorization, s)
    sale = require_sale(s, sale_id)
    item = s.query(AdminSaleInstallment).filter_by(id=installment_id, sale_id=sale.id).first()
    if not item:
        raise HTTPException(404, 'Parcela não encontrada')
    item.status = 'paid'
    item.paid_amount = item.amount
    item.paid_at = parse_date(payment_date, 'data do pagamento', optional=True) or date.today()
    s.commit()
    open_count = s.query(AdminSaleInstallment).filter(
        AdminSaleInstallment.sale_id == sale.id,
        AdminSaleInstallment.status != 'paid',
    ).count()
    if open_count == 0:
        sale.status = 'paid'
        s.commit()
    return {'ok': True}


@router.post('/api/sales/{sale_id}/installments/{installment_id}/mark-unpaid')
def mark_sale_unpaid(
    sale_id: int,
    installment_id: int,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    require_admin_user(authorization, s)
    sale = require_sale(s, sale_id)
    item = s.query(AdminSaleInstallment).filter_by(id=installment_id, sale_id=sale.id).first()
    if not item:
        raise HTTPException(404, 'Parcela não encontrada')
    item.status = 'pending'
    item.paid_amount = 0
    item.paid_at = None
    sale.status = 'active'
    s.commit()
    return {'ok': True}


@router.get('/vendas/contrato-admin/{share_token}.pdf')
def public_contract(share_token: str, s: Session = Depends(db)):
    sale = s.query(AdminSale).filter_by(share_token=share_token).first()
    if not sale:
        raise HTTPException(404, 'Contrato não encontrado')
    pdf = build_contract_pdf(s, sale)
    return StreamingResponse(
        pdf,
        media_type='application/pdf',
        headers={'Content-Disposition': f'inline; filename="contrato-{sale.number}.pdf"'},
    )


@router.post('/api/sales/{sale_id}/send-contract')
def send_contract(
    sale_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    require_admin_user(authorization, s)
    sale = require_sale(s, sale_id)
    client = s.get(Client, sale.client_id)
    if not client:
        raise HTTPException(404, 'Cliente não encontrado')

    number = only_digits(client.whatsapp or client.phone)
    if len(number) in (10, 11):
        number = '55' + number
    if len(number) < 12:
        raise HTTPException(400, 'Cadastre um WhatsApp válido com DDD no cliente')

    url = f'{public_base(request)}/vendas/contrato-admin/{sale.share_token}.pdf'
    result = send_whatsapp_document(
        number,
        url,
        f'contrato-{sale.number}.pdf',
        f'Olá, {client.name}. Segue o contrato de compra e venda de {sale.item_name}, no valor de {money_br(sale.sale_value)}.',
    )
    message_id = ''
    try:
        message_id = (result.get('messages') or [{}])[0].get('id', '')
    except Exception:
        pass
    return {'ok': True, 'message_id': message_id, 'contract_url': url}
