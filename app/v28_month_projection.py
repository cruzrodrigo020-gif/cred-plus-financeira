"""Forecast of scheduled, unpaid receivables for the rest of the current month."""
import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.v12_helpers import db
from app.v12_models import Client, Contract, Installment
from app.v25_admin_sales import AdminSale, AdminSaleInstallment, require_admin_user

router = APIRouter()


def _cents(value):
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _amount(cents):
    return round(cents / 100, 2)


def _interest_part(remaining_cents, principal_cents, total_cents):
    """Estimate interest embedded in an unpaid instalment, proportional to contract total."""
    if total_cents <= 0:
        return 0
    interest_cents = max(0, total_cents - principal_cents)
    return min(remaining_cents, (remaining_cents * interest_cents + total_cents // 2) // total_cents)


@router.get('/api/projections/month-end')
def month_end_projection(
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    require_admin_user(authorization, s)
    today = date.today()
    last = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    groups = {
        'loans': {'label': 'Empréstimos (juros)', 'items': []},
        'agreements': {'label': 'Acordos', 'items': []},
        'sales': {'label': 'Vendas', 'items': []},
    }
    overdue = {'loans': 0, 'agreements': 0, 'sales': 0}

    # Loans and agreements are different categories of the same contract table.
    contracts = s.query(Contract).filter(Contract.status == 'active').all()
    client_ids = set(c.client_id for c in contracts)
    sales = s.query(AdminSale).filter(AdminSale.status == 'active').all()
    client_ids.update(x.client_id for x in sales)
    clients = {c.id: c.name for c in s.query(Client).filter(Client.id.in_(client_ids)).all()} if client_ids else {}

    if contracts:
        contract_ids = [c.id for c in contracts]
        all_items = s.query(Installment).filter(Installment.contract_id.in_(contract_ids)).all()
        by_contract = defaultdict(list)
        for item in all_items:
            by_contract[item.contract_id].append(item)
        for contract in contracts:
            kind = 'agreements' if contract.periodicity == 'monthly' else 'loans'
            total_cents = _cents(contract.total)
            principal_cents = _cents(contract.principal)
            for item in by_contract.get(contract.id, []):
                remaining = max(0, _cents(item.amount) - _cents(item.paid_amount))
                if item.status == 'paid' or remaining == 0:
                    continue
                interest = _interest_part(remaining, principal_cents, total_cents)
                if item.due_date < today:
                    overdue[kind] += remaining
                    continue
                if item.due_date > last:
                    continue
                groups[kind]['items'].append({
                    'date': str(item.due_date),
                    'client': clients.get(contract.client_id, '-'),
                    'contract': contract.number,
                    'contract_id': contract.id,
                    'installment': item.number,
                    'periodicity': contract.periodicity,
                    'rate': round(float(contract.rate or 0), 2),
                    'amount': _amount(remaining),
                    'interest': _amount(interest),
                    'capital': _amount(max(0, remaining - interest)),
                })

    if sales:
        sale_ids = [x.id for x in sales]
        sale_items = s.query(AdminSaleInstallment).filter(AdminSaleInstallment.sale_id.in_(sale_ids)).all()
        by_sale = defaultdict(list)
        for item in sale_items:
            by_sale[item.sale_id].append(item)
        for sale in sales:
            for item in by_sale.get(sale.id, []):
                remaining = max(0, _cents(item.amount) - _cents(item.paid_amount))
                if item.status == 'paid' or remaining == 0:
                    continue
                if item.due_date < today:
                    overdue['sales'] += remaining
                    continue
                if item.due_date > last:
                    continue
                groups['sales']['items'].append({
                    'date': str(item.due_date),
                    'client': clients.get(sale.client_id, '-'),
                    'contract': sale.number,
                    'contract_id': sale.id,
                    'installment': item.number,
                    'product': sale.item_name,
                    'amount': _amount(remaining),
                })

    results = {}
    daily = defaultdict(lambda: {'loans_interest': 0, 'loans_gross': 0, 'agreements': 0, 'sales': 0})
    for name, group in groups.items():
        items = sorted(group['items'], key=lambda x: (x['date'], x['client'].lower(), x['contract'], x['installment']))
        gross = sum(_cents(x['amount']) for x in items)
        interest = sum(_cents(x.get('interest', 0)) for x in items)
        for x in items:
            day = daily[x['date']]
            if name == 'loans':
                day['loans_interest'] += _cents(x['interest'])
                day['loans_gross'] += _cents(x['amount'])
            else:
                day[name] += _cents(x['amount'])
        results[name] = {
            'label': group['label'],
            'total': _amount(interest if name == 'loans' else gross),
            'gross': _amount(gross),
            'interest': _amount(interest),
            'capital': _amount(gross - interest) if name != 'sales' else None,
            'count': len(items),
            'contracts': len({x['contract_id'] for x in items}),
            'overdue': _amount(overdue[name]),
            'items': items,
        }
    days = []
    for dt, values in sorted(daily.items()):
        row = {'date': dt}
        row.update({key: _amount(value) for key, value in values.items()})
        row['total'] = _amount(values['loans_interest'] + values['agreements'] + values['sales'])
        days.append(row)

    return {
        'as_of': str(today),
        'through': str(last),
        'method': 'Somente parcelas com vencimento entre hoje e o último dia do mês, com saldo não pago. Juros dos empréstimos estimados proporcionalmente ao valor de juros embutido em cada contrato.',
        'loans': results['loans'],
        'agreements': results['agreements'],
        'sales': results['sales'],
        'total_projected': _amount(_cents(results['loans']['total']) + _cents(results['agreements']['total']) + _cents(results['sales']['total'])),
        'daily': days,
    }
