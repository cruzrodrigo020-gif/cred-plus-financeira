from io import BytesIO
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from app.v12_models import Client, Contract, Installment, Payment, Product, User
from app.v12_helpers import db, current_user, require_admin

router = APIRouter()


def brl(value):
    return ('R$ {:,.2f}'.format(float(value or 0))).replace(',', 'X').replace('.', ',').replace('X', '.')


def fmt_date(value):
    if not value:
        return '-'
    if hasattr(value, 'strftime'):
        return value.strftime('%d/%m/%Y')
    return str(value)


def contract_type(periodicity):
    return {
        'daily': 'Emprestimo diario',
        'final': 'Emprestimo com pagamento final',
        'monthly': 'Acordo mensal',
    }.get(periodicity, 'Emprestimo')


def _contract_received(s: Session, contract_id: int):
    return round(sum(float(p.amount or 0) for p in s.query(Payment).filter_by(contract_id=contract_id).all()), 2)


def _record(s: Session, c: Contract):
    client = s.get(Client, c.client_id)
    product = s.get(Product, c.product_id)
    collector = s.get(User, c.collector_id) if c.collector_id else None
    received = _contract_received(s, c.id)
    return {
        'id': c.id,
        'number': c.number,
        'date': c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
        'client': client.name if client else '-',
        'cpf': client.cpf if client else '',
        'whatsapp': client.whatsapp if client else '',
        'principal': round(float(c.principal or 0), 2),
        'rate': round(float(c.rate or 0), 2),
        'total': round(float(c.total or 0), 2),
        'received': received,
        'balance': round(max(0, float(c.total or 0) - received), 2),
        'installments': c.installments,
        'first_due': str(c.first_due) if c.first_due else '',
        'periodicity': c.periodicity,
        'type': contract_type(c.periodicity),
        'product': product.name if product else contract_type(c.periodicity),
        'collector': collector.name if collector else 'Administracao',
        'status': c.status,
    }


@router.get('/api/reports/contracts')
def report_contracts(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    require_admin(u)
    contracts = s.query(Contract).order_by(Contract.created_at.desc(), Contract.id.desc()).all()
    return [_record(s, c) for c in contracts]


def _header_footer(canvas, doc):
    canvas.saveState()
    width, height = doc.pagesize
    canvas.setFillColor(colors.HexColor('#0f172a'))
    canvas.rect(0, height - 18 * mm, width, 18 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 13)
    canvas.drawString(14 * mm, height - 11 * mm, 'CRED+ FINANCEIRA')
    canvas.setFont('Helvetica', 7.5)
    canvas.drawRightString(width - 14 * mm, 8 * mm, f'Pagina {doc.page}')
    canvas.drawString(14 * mm, 8 * mm, 'Documento gerado automaticamente pelo sistema CRED+ Financeira.')
    canvas.restoreState()


@router.get('/api/reports/contracts.pdf')
def report_all_contracts_pdf(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    require_admin(u)
    records = [_record(s, c) for c in s.query(Contract).order_by(Contract.created_at.desc(), Contract.id.desc()).all()]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=25 * mm, bottomMargin=14 * mm,
        title='Relatorio geral de emprestimos - CRED+ Financeira',
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle('RptTitle', parent=styles['Title'], fontName='Helvetica-Bold',
                           fontSize=17, leading=20, textColor=colors.HexColor('#0f172a'), spaceAfter=3 * mm)
    small = ParagraphStyle('Small', parent=styles['BodyText'], fontSize=8, leading=10)
    story = [
        Paragraph('Relatorio geral de emprestimos e acordos', title),
        Paragraph(f'Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} - Total de registros: {len(records)}', small),
        Spacer(1, 4 * mm),
    ]

    data = [['Data', 'Cliente', 'Contrato', 'Tipo', 'Principal', 'Juros', 'Total', 'Recebido', 'Saldo', 'Parcelas', 'Status']]
    for r in records:
        data.append([
            fmt_date(r['date']),
            Paragraph(str(r['client']), small),
            r['number'],
            Paragraph(r['type'], small),
            brl(r['principal']),
            f"{r['rate']:.2f}%",
            brl(r['total']),
            brl(r['received']),
            brl(r['balance']),
            str(r['installments']),
            str(r['status']),
        ])
    if len(data) == 1:
        data.append(['-', 'Nenhum registro', '-', '-', '-', '-', '-', '-', '-', '-', '-'])

    table = Table(data, repeatRows=1, colWidths=[19*mm, 37*mm, 31*mm, 34*mm, 24*mm, 15*mm, 24*mm, 24*mm, 24*mm, 17*mm, 20*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7.5),
        ('FONTSIZE', (0,1), (-1,-1), 7),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.35, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('LEFTPADDING', (0,0), (-1,-1), 3),
        ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(table)

    total_principal = sum(r['principal'] for r in records)
    total_contracts = sum(r['total'] for r in records)
    total_received = sum(r['received'] for r in records)
    total_balance = sum(r['balance'] for r in records)
    story += [
        Spacer(1, 5 * mm),
        Table([
            ['Capital emprestado', brl(total_principal), 'Total contratado', brl(total_contracts),
             'Recebido', brl(total_received), 'Saldo a receber', brl(total_balance)]
        ], colWidths=[30*mm, 30*mm, 30*mm, 30*mm, 22*mm, 30*mm, 30*mm, 30*mm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#eef2ff')),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BOX', (0,0), (-1,-1), .5, colors.HexColor('#94a3b8')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ]))
    ]

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="cred-plus-relatorio-geral-emprestimos.pdf"'}
    )


@router.get('/api/reports/contracts/{contract_id}.pdf')
def report_contract_pdf(contract_id: int, authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    u = current_user(authorization, s)
    require_admin(u)
    c = s.get(Contract, contract_id)
    if not c:
        raise HTTPException(404, 'Contrato nao encontrado')
    r = _record(s, c)
    client = s.get(Client, c.client_id)
    installments = s.query(Installment).filter_by(contract_id=c.id).order_by(Installment.number).all()
    payments = s.query(Payment).filter_by(contract_id=c.id).order_by(Payment.payment_date, Payment.id).all()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
        topMargin=25*mm, bottomMargin=14*mm,
        title=f'Emprestimo {c.number} - CRED+ Financeira'
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle('DetailTitle', parent=styles['Title'], fontName='Helvetica-Bold',
                           fontSize=17, leading=20, textColor=colors.HexColor('#0f172a'), spaceAfter=3*mm)
    label = ParagraphStyle('Label', parent=styles['BodyText'], fontSize=8, leading=10, textColor=colors.HexColor('#475569'))
    body = ParagraphStyle('Body', parent=styles['BodyText'], fontSize=9, leading=11)
    section = ParagraphStyle('Section', parent=styles['Heading2'], fontName='Helvetica-Bold',
                             fontSize=11, textColor=colors.HexColor('#1e3a8a'), spaceBefore=4*mm, spaceAfter=2*mm)

    story = [
        Paragraph('Ficha completa do emprestimo', title),
        Paragraph(f'Contrato {c.number} - emitido em {datetime.now().strftime("%d/%m/%Y %H:%M")}', label),
        Spacer(1, 4*mm),
        Paragraph('Dados do cliente', section),
    ]

    info = [
        ['Nome', r['client'], 'CPF', r['cpf'] or '-'],
        ['WhatsApp', r['whatsapp'] or '-', 'Cobrador', r['collector']],
        ['Data do emprestimo', fmt_date(c.created_at), 'Status', r['status']],
        ['Modalidade', r['type'], 'Produto', r['product']],
        ['Valor emprestado', brl(r['principal']), 'Juros', f"{r['rate']:.2f}%"],
        ['Valor total', brl(r['total']), 'Recebido', brl(r['received'])],
        ['Saldo a receber', brl(r['balance']), 'Parcelas', str(r['installments'])],
        ['Primeiro vencimento', fmt_date(c.first_due), 'Valor medio da parcela', brl(c.installment_value)],
    ]
    t = Table(info, colWidths=[31*mm, 57*mm, 31*mm, 57*mm])
    t.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), .35, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#f1f5f9')),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)

    story.append(Paragraph('Parcelas', section))
    inst_data = [['Nº', 'Vencimento', 'Valor', 'Pago', 'Saldo', 'Status', 'Data pagamento']]
    for i in installments:
        inst_data.append([
            str(i.number), fmt_date(i.due_date), brl(i.amount), brl(i.paid_amount),
            brl(max(0, float(i.amount or 0) - float(i.paid_amount or 0))),
            i.status, fmt_date(i.paid_at),
        ])
    it = Table(inst_data, repeatRows=1, colWidths=[12*mm, 28*mm, 27*mm, 27*mm, 27*mm, 25*mm, 30*mm])
    it.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 7.5),
        ('GRID', (0,0), (-1,-1), .35, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(it)

    story.append(Paragraph('Pagamentos registrados', section))
    pay_data = [['Data', 'Valor', 'Forma', 'Parcela', 'Observacao']]
    if payments:
        for p in payments:
            inst = s.get(Installment, p.installment_id)
            pay_data.append([
                fmt_date(p.payment_date), brl(p.amount), p.method or '-',
                str(inst.number) if inst else '-', Paragraph(p.note or '-', body)
            ])
    else:
        pay_data.append(['-', '-', '-', '-', 'Nenhum pagamento registrado'])
    pt = Table(pay_data, repeatRows=1, colWidths=[28*mm, 28*mm, 28*mm, 18*mm, 74*mm])
    pt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f766e')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 7.5),
        ('GRID', (0,0), (-1,-1), .35, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(pt)
    story += [Spacer(1, 5*mm), Paragraph('Este documento representa o historico registrado no sistema ate o momento da emissao.', label)]

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buf.seek(0)
    safe_number = ''.join(ch for ch in c.number if ch.isalnum() or ch in ('-', '_'))
    return StreamingResponse(
        buf, media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="emprestimo-{safe_number}.pdf"'}
    )
