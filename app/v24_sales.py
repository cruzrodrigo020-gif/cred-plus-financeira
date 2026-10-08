import calendar
import json
import os
import secrets
import textwrap
import urllib.error
import urllib.request
from io import BytesIO
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.v12_models import Base, engine
from app.v12_helpers import db, parse_date
from app.v15_lender import (
    LenderAccount,
    LenderClient,
    current_lender,
    digits,
)

router = APIRouter()


class LenderSale(Base):
    __tablename__ = 'lender_sales'

    id: Mapped[int] = mapped_column(primary_key=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey('lender_accounts.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('lender_clients.id'), index=True)
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


class LenderSaleInstallment(Base):
    __tablename__ = 'lender_sale_installments'

    id: Mapped[int] = mapped_column(primary_key=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey('lender_accounts.id'), index=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey('lender_sales.id'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    paid_amount: Mapped[float] = mapped_column(Float, default=0)
    paid_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


Base.metadata.create_all(engine)


def money_br(value: float) -> str:
    s = f'{float(value or 0):,.2f}'
    return 'R$ ' + s.replace(',', 'X').replace('.', ',').replace('X', '.')


def add_months(value: date, months: int) -> date:
    idx = value.month - 1 + months
    year = value.year + idx // 12
    month = idx % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def require_sale(s: Session, lender_id: int, sale_id: int) -> LenderSale:
    sale = s.query(LenderSale).filter_by(id=sale_id, lender_id=lender_id).first()
    if not sale:
        raise HTTPException(404, 'Venda não encontrada')
    return sale


def require_sale_installment(s: Session, lender_id: int, sale_id: int, installment_id: int) -> LenderSaleInstallment:
    item = s.query(LenderSaleInstallment).filter_by(
        id=installment_id,
        lender_id=lender_id,
        sale_id=sale_id,
    ).first()
    if not item:
        raise HTTPException(404, 'Parcela da venda não encontrada')
    return item


def sale_to_dict(s: Session, sale: LenderSale):
    client = s.get(LenderClient, sale.client_id)
    paid = s.query(LenderSaleInstallment).filter_by(
        lender_id=sale.lender_id,
        sale_id=sale.id,
        status='paid',
    ).count()
    return {
        'id': sale.id,
        'number': sale.number,
        'client_id': sale.client_id,
        'client': client.name if client else '-',
        'client_whatsapp': client.whatsapp if client else '',
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


def build_contract_pdf(s: Session, sale: LenderSale) -> BytesIO:
    seller = s.get(LenderAccount, sale.lender_id)
    buyer = s.get(LenderClient, sale.client_id)
    items = s.query(LenderSaleInstallment).filter_by(
        lender_id=sale.lender_id,
        sale_id=sale.id,
    ).order_by(LenderSaleInstallment.number).all()

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    pdf.setTitle(f'Contrato de Compra e Venda {sale.number}')

    left = 48
    right = width - 48
    y = height - 52

    def new_page():
        nonlocal y
        pdf.showPage()
        y = height - 52

    def ensure(space=40):
        nonlocal y
        if y < 70 + space:
            new_page()

    def line(text='', bold=False, size=10, gap=15):
        nonlocal y
        ensure(gap + 5)
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        pdf.drawString(left, y, str(text))
        y -= gap

    def paragraph(text, bold=False, size=10, gap=14):
        nonlocal y
        chars = 94 if size <= 10 else 82
        for row in textwrap.wrap(str(text), width=chars, break_long_words=False, break_on_hyphens=False) or ['']:
            line(row, bold=bold, size=size, gap=gap)
        y -= 4

    pdf.setFont('Helvetica-Bold', 17)
    pdf.drawCentredString(width / 2, y, 'INSTRUMENTO PARTICULAR DE COMPRA E VENDA')
    y -= 22
    pdf.setFont('Helvetica', 9)
    pdf.drawCentredString(width / 2, y, f'Contrato nº {sale.number}')
    y -= 26
    pdf.line(left, y, right, y)
    y -= 24

    seller_name = seller.name if seller else 'Vendedor'
    seller_cpf = seller.cpf if seller else ''
    seller_address = ', '.join(x for x in [
        seller.address if seller else '',
        seller.city if seller else '',
        seller.state if seller else '',
    ] if x) or 'não informado'

    buyer_name = buyer.name if buyer else 'Comprador'
    buyer_cpf = buyer.cpf if buyer else ''
    buyer_address = ', '.join(x for x in [
        buyer.address if buyer else '',
        buyer.city if buyer else '',
        buyer.state if buyer else '',
    ] if x) or 'não informado'

    paragraph(
        f'VENDEDOR(A): {seller_name}, CPF {seller_cpf or "não informado"}, endereço {seller_address}.',
        bold=True,
    )
    paragraph(
        f'COMPRADOR(A): {buyer_name}, CPF {buyer_cpf or "não informado"}, endereço {buyer_address}.',
        bold=True,
    )

    line('1. OBJETO DA COMPRA E VENDA', bold=True, size=11, gap=17)
    paragraph(
        f'O(A) VENDEDOR(A) declara vender ao(à) COMPRADOR(A) o seguinte item: {sale.item_name}. '
        + (f'Descrição: {sale.item_description}. ' if sale.item_description else '')
        + 'O comprador declara ter ciência do objeto negociado e das condições registradas neste instrumento.'
    )

    line('2. PREÇO E FORMA DE PAGAMENTO', bold=True, size=11, gap=17)
    paragraph(
        f'O preço total ajustado é de {money_br(sale.sale_value)}, dividido em {sale.installments} '
        f'parcela(s), conforme cronograma abaixo. Não há juros adicionais além do valor total registrado nesta venda.'
    )

    line('CRONOGRAMA DE PARCELAS', bold=True, size=10, gap=17)
    pdf.setFont('Helvetica-Bold', 9)
    pdf.drawString(left, y, 'Parcela')
    pdf.drawString(left + 90, y, 'Vencimento')
    pdf.drawString(left + 210, y, 'Valor')
    pdf.drawString(left + 330, y, 'Situação')
    y -= 14
    pdf.line(left, y, right, y)
    y -= 14
    for item in items:
        ensure(25)
        pdf.setFont('Helvetica', 9)
        pdf.drawString(left, y, str(item.number))
        pdf.drawString(left + 90, y, item.due_date.strftime('%d/%m/%Y'))
        pdf.drawString(left + 210, y, money_br(item.amount))
        pdf.drawString(left + 330, y, 'Paga' if item.status == 'paid' else 'Pendente')
        y -= 16
    y -= 8

    line('3. ENTREGA E RESPONSABILIDADE PELO BEM', bold=True, size=11, gap=17)
    paragraph(
        'As partes declaram que a entrega, condição, características e eventuais garantias do item são aquelas '
        'acordadas entre vendedor e comprador. Qualquer condição adicional deverá ser formalizada por escrito.'
    )

    line('4. INADIMPLEMENTO', bold=True, size=11, gap=17)
    paragraph(
        'O não pagamento de qualquer parcela no vencimento caracteriza atraso. Eventuais multas, juros, '
        'renegociações ou outras medidas somente poderão ser exigidos quando previamente acordados e permitidos pela legislação aplicável.'
    )

    line('5. DISPOSIÇÕES GERAIS', bold=True, size=11, gap=17)
    paragraph(
        'Este instrumento registra os dados informados pelas partes no sistema CRED+ Financeira. '
        'As partes devem conferir todas as informações antes da assinatura. Alterações posteriores devem ser documentadas por escrito.'
    )

    city = (seller.city if seller else '') or (buyer.city if buyer else '') or '________________'
    state = (seller.state if seller else '') or (buyer.state if buyer else '')
    line('6. FORO', bold=True, size=11, gap=17)
    paragraph(
        f'Fica eleito o foro da comarca de {city}{"/" + state if state else ""}, quando permitido pela legislação, '
        'sem prejuízo de eventual foro legalmente obrigatório.'
    )

    ensure(150)
    y -= 10
    pdf.line(left, y, left + 190, y)
    pdf.line(right - 190, y, right, y)
    y -= 15
    pdf.setFont('Helvetica', 9)
    pdf.drawCentredString(left + 95, y, seller_name[:45])
    pdf.drawCentredString(right - 95, y, buyer_name[:45])
    y -= 13
    pdf.drawCentredString(left + 95, y, 'VENDEDOR(A)')
    pdf.drawCentredString(right - 95, y, 'COMPRADOR(A)')
    y -= 28
    pdf.setFont('Helvetica', 8)
    pdf.drawString(left, y, f'Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} pelo sistema CRED+ Financeira.')
    y -= 12
    pdf.drawString(left, y, 'Documento gerado automaticamente. Recomenda-se revisão das partes antes da assinatura.')

    pdf.save()
    buf.seek(0)
    return buf


def whatsapp_number(raw: str) -> str:
    number = digits(raw)
    if len(number) in (10, 11):
        number = '55' + number
    if len(number) < 12:
        raise HTTPException(400, 'O cliente não possui um WhatsApp válido com DDD.')
    return number


def send_whatsapp_document(to_number: str, document_url: str, filename: str, caption: str):
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip()
    phone_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    version = os.getenv('WHATSAPP_GRAPH_VERSION', 'v23.0').strip() or 'v23.0'
    if not token or not phone_id:
        raise HTTPException(503, 'A integração do WhatsApp ainda não está configurada no servidor.')

    payload = json.dumps({
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': to_number,
        'type': 'document',
        'document': {
            'link': document_url,
            'caption': caption[:1024],
            'filename': filename,
        },
    }).encode('utf-8')

    req = urllib.request.Request(
        f'https://graph.facebook.com/{version}/{phone_id}/messages',
        data=payload,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            body = response.read().decode('utf-8', errors='replace')
            data = json.loads(body or '{}')
            return data
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(raw).get('error', {}).get('message') or raw
        except Exception:
            detail = raw
        raise HTTPException(502, f'WhatsApp não aceitou o envio: {str(detail)[:240]}')
    except Exception as exc:
        raise HTTPException(502, f'Não foi possível enviar pelo WhatsApp: {str(exc)[:180]}')


@router.get('/api/lender/sales')
def lender_sales(
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    rows = s.query(LenderSale).filter_by(lender_id=account.id).order_by(LenderSale.id.desc()).all()
    return [sale_to_dict(s, x) for x in rows]


@router.post('/api/lender/sales')
def lender_create_sale(
    client_id: int = Form(...),
    item_name: str = Form(...),
    item_description: str = Form(''),
    sale_value: float = Form(...),
    installments: int = Form(...),
    first_due: str = Form(...),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    client = s.query(LenderClient).filter_by(id=client_id, lender_id=account.id).first()
    if not client:
        raise HTTPException(404, 'Cliente não encontrado')
    item_name = item_name.strip()
    if len(item_name) < 2:
        raise HTTPException(400, 'Informe o item que está sendo vendido.')
    if sale_value <= 0:
        raise HTTPException(400, 'O valor da venda deve ser maior que zero.')
    if installments < 1 or installments > 12:
        raise HTTPException(400, 'Escolha de 1 a 12 parcelas.')

    due = parse_date(first_due, 'primeiro vencimento')
    total_cents = int(round(sale_value * 100))
    base_cents = total_cents // installments
    values = [base_cents / 100 for _ in range(installments)]
    values[-1] = round(sale_value - sum(values[:-1]), 2)

    number = f'VEN-{account.id}-{datetime.now().strftime("%y%m%d%H%M%S%f")[-12:]}'
    sale = LenderSale(
        lender_id=account.id,
        client_id=client.id,
        number=number,
        item_name=item_name,
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

    for idx in range(installments):
        s.add(LenderSaleInstallment(
            lender_id=account.id,
            sale_id=sale.id,
            number=idx + 1,
            due_date=add_months(due, idx),
            amount=values[idx],
            status='pending',
            paid_amount=0,
        ))

    s.commit()
    s.refresh(sale)
    return sale_to_dict(s, sale)


@router.get('/api/lender/sales/{sale_id}')
def lender_sale_detail(
    sale_id: int,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    sale = require_sale(s, account.id, sale_id)
    data = sale_to_dict(s, sale)
    data['items'] = [
        {
            'id': i.id,
            'number': i.number,
            'due_date': str(i.due_date),
            'amount': i.amount,
            'status': i.status,
            'paid_amount': i.paid_amount,
            'paid_at': str(i.paid_at) if i.paid_at else '',
        }
        for i in s.query(LenderSaleInstallment).filter_by(
            lender_id=account.id,
            sale_id=sale.id,
        ).order_by(LenderSaleInstallment.number).all()
    ]
    return data


@router.post('/api/lender/sales/{sale_id}/installments/{installment_id}/mark-paid')
def lender_sale_mark_paid(
    sale_id: int,
    installment_id: int,
    payment_date: str = Form(''),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    sale = require_sale(s, account.id, sale_id)
    item = require_sale_installment(s, account.id, sale.id, installment_id)
    paid = parse_date(payment_date, 'data do pagamento', optional=True) or date.today()
    item.status = 'paid'
    item.paid_amount = item.amount
    item.paid_at = paid
    s.commit()

    pending = s.query(LenderSaleInstallment).filter(
        LenderSaleInstallment.lender_id == account.id,
        LenderSaleInstallment.sale_id == sale.id,
        LenderSaleInstallment.status != 'paid',
    ).count()
    if pending == 0:
        sale.status = 'paid'
        s.commit()
    return {'ok': True}


@router.post('/api/lender/sales/{sale_id}/installments/{installment_id}/mark-unpaid')
def lender_sale_mark_unpaid(
    sale_id: int,
    installment_id: int,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    sale = require_sale(s, account.id, sale_id)
    item = require_sale_installment(s, account.id, sale.id, installment_id)
    item.status = 'pending'
    item.paid_amount = 0
    item.paid_at = None
    sale.status = 'active'
    s.commit()
    return {'ok': True}


@router.get('/api/lender/sales/{sale_id}/contract.pdf')
def lender_sale_contract(
    sale_id: int,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    sale = require_sale(s, account.id, sale_id)
    pdf = build_contract_pdf(s, sale)
    headers = {'Content-Disposition': f'inline; filename="contrato-{sale.number}.pdf"'}
    return StreamingResponse(pdf, media_type='application/pdf', headers=headers)


@router.get('/vendas/contrato/{share_token}.pdf')
def public_sale_contract(share_token: str, s: Session = Depends(db)):
    sale = s.query(LenderSale).filter_by(share_token=share_token).first()
    if not sale:
        raise HTTPException(404, 'Contrato não encontrado')
    pdf = build_contract_pdf(s, sale)
    headers = {'Content-Disposition': f'inline; filename="contrato-{sale.number}.pdf"'}
    return StreamingResponse(pdf, media_type='application/pdf', headers=headers)


@router.post('/api/lender/sales/{sale_id}/send-contract')
def lender_send_sale_contract(
    sale_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    account = current_lender(authorization, s)
    sale = require_sale(s, account.id, sale_id)
    client = s.query(LenderClient).filter_by(id=sale.client_id, lender_id=account.id).first()
    if not client:
        raise HTTPException(404, 'Cliente não encontrado')

    to_number = whatsapp_number(client.whatsapp or client.phone)
    public_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()
    base = f'https://{public_domain}' if public_domain else str(request.base_url).rstrip('/')
    document_url = f'{base}/vendas/contrato/{sale.share_token}.pdf'
    result = send_whatsapp_document(
        to_number,
        document_url,
        f'contrato-{sale.number}.pdf',
        f'Olá, {client.name}. Segue o contrato de compra e venda referente a {sale.item_name}, no valor de {money_br(sale.sale_value)}.',
    )
    message_id = ''
    try:
        message_id = (result.get('messages') or [{}])[0].get('id', '')
    except Exception:
        pass
    return {'ok': True, 'message_id': message_id, 'contract_url': document_url}
