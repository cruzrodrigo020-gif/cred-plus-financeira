from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.v12_models import Base, engine, User, Client, Contract, Installment, Payment
from app.v12_helpers import db, current_user, require_admin, log, parse_date

router = APIRouter()


class CollectorGoal(Base):
    __tablename__ = 'collector_goals'
    __table_args__ = (UniqueConstraint('collector_id', 'month_key', name='uq_collector_goal_month'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    month_key: Mapped[str] = mapped_column(String(7), index=True)
    target_amount: Mapped[float] = mapped_column(Float, default=0)
    commission_rate: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CollectorRouteStop(Base):
    __tablename__ = 'collector_route_stops'
    __table_args__ = (UniqueConstraint('collector_id', 'client_id', 'route_date', name='uq_route_client_day'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    route_date: Mapped[date] = mapped_column(Date, index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    scheduled_time: Mapped[str] = mapped_column(String(5), default='')
    status: Mapped[str] = mapped_column(String(30), default='pending')
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Base.metadata.create_all(engine)


def month_bounds(month_key: str):
    try:
        year, month = [int(x) for x in month_key.split('-')]
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        return start, end
    except Exception:
        raise HTTPException(400, 'Mês inválido. Use AAAA-MM.')


def month_key_or_current(value: str):
    value = (value or '').strip()
    if not value:
        return date.today().strftime('%Y-%m')
    month_bounds(value)
    return value


def collector_or_403(s: Session, user: User, collector_id: Optional[int]):
    cid = collector_id if user.role == 'admin' and collector_id else user.id
    collector = s.get(User, cid)
    if not collector or collector.role != 'collector':
        raise HTTPException(400, 'Cobrador inválido')
    if user.role != 'admin' and cid != user.id:
        raise HTTPException(403, 'Acesso negado')
    return collector


def paid_for_collector(s: Session, collector_id: int, start: date, end: date):
    return sum(
        p.amount for p in s.query(Payment).filter(
            Payment.collector_id == collector_id,
            Payment.payment_date >= start,
            Payment.payment_date <= end,
        ).all()
    )


def goal_row(s: Session, collector: User, month_key: str):
    start, end = month_bounds(month_key)
    goal = s.query(CollectorGoal).filter_by(collector_id=collector.id, month_key=month_key).first()
    target = goal.target_amount if goal else 0
    rate = goal.commission_rate if goal else 0
    collected = paid_for_collector(s, collector.id, start, end)
    progress = round((collected / target * 100), 1) if target > 0 else 0
    commission = round(collected * rate / 100, 2)
    remaining = max(0, target - collected)
    days_in_month = (end - start).days + 1
    day_index = min(max((date.today() - start).days + 1, 0), days_in_month) if start <= date.today() <= end else days_in_month
    pace_target = target * (day_index / days_in_month) if target > 0 else 0
    pace_status = 'ahead' if collected >= pace_target else 'behind'
    return {
        'collector_id': collector.id,
        'collector': collector.name,
        'username': collector.username,
        'month': month_key,
        'target': target,
        'commission_rate': rate,
        'collected': collected,
        'progress': progress,
        'remaining': remaining,
        'commission': commission,
        'pace_target': round(pace_target, 2),
        'pace_status': pace_status,
        'goal_configured': bool(goal),
    }


@router.get('/api/goals')
def goals(month: str = '', authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    user = current_user(authorization, s)
    month_key = month_key_or_current(month)
    q = s.query(User).filter(User.role == 'collector')
    if user.role != 'admin':
        q = q.filter(User.id == user.id)
    collectors = q.order_by(User.name).all()
    return [goal_row(s, c, month_key) for c in collectors]


@router.post('/api/goals')
def save_goal(
    collector_id: int = Form(...), month: str = Form(...), target_amount: float = Form(...),
    commission_rate: float = Form(0), authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    user = current_user(authorization, s)
    require_admin(user)
    month_key = month_key_or_current(month)
    collector = s.get(User, collector_id)
    if not collector or collector.role != 'collector':
        raise HTTPException(400, 'Cobrador inválido')
    if target_amount < 0 or commission_rate < 0 or commission_rate > 100:
        raise HTTPException(400, 'Meta ou comissão inválida')
    goal = s.query(CollectorGoal).filter_by(collector_id=collector_id, month_key=month_key).first()
    if not goal:
        goal = CollectorGoal(collector_id=collector_id, month_key=month_key)
        s.add(goal)
    goal.target_amount = target_amount
    goal.commission_rate = commission_rate
    s.commit()
    log(s, user, 'COLLECTOR_GOAL', f'{collector_id}:{month_key}:{target_amount}:{commission_rate}')
    return goal_row(s, collector, month_key)


def client_pending_snapshot(s: Session, collector_id: int, client_id: int, ref_date: date):
    items = s.query(Installment).join(Contract).filter(
        Contract.collector_id == collector_id,
        Contract.client_id == client_id,
        Installment.status != 'paid',
    ).all()
    overdue_items = [i for i in items if i.due_date < ref_date]
    today_items = [i for i in items if i.due_date == ref_date]
    total_pending = sum(max(0, i.amount - i.paid_amount) for i in items)
    due_today = sum(max(0, i.amount - i.paid_amount) for i in today_items)
    overdue = sum(max(0, i.amount - i.paid_amount) for i in overdue_items)
    max_days = max([(ref_date - i.due_date).days for i in overdue_items], default=0)
    return total_pending, due_today, overdue, max_days


def stop_dict(s: Session, stop: CollectorRouteStop):
    client = s.get(Client, stop.client_id)
    total_pending, due_today, overdue, max_days = client_pending_snapshot(s, stop.collector_id, stop.client_id, stop.route_date)
    priority = 'high' if max_days >= 15 or overdue >= 500 else ('medium' if max_days > 0 or due_today >= 300 else 'normal')
    address = ''
    if client:
        parts = [client.street, client.address_number, client.neighborhood, client.city, client.state]
        address = ', '.join([str(x).strip() for x in parts if x and str(x).strip()]) or client.address or ''
    return {
        'id': stop.id,
        'collector_id': stop.collector_id,
        'client_id': stop.client_id,
        'client': client.name if client else '-',
        'whatsapp': (client.whatsapp or client.phone) if client else '',
        'address': address,
        'route_date': str(stop.route_date),
        'position': stop.position,
        'scheduled_time': stop.scheduled_time,
        'status': stop.status,
        'note': stop.note,
        'pending': total_pending,
        'due_today': due_today,
        'overdue': overdue,
        'overdue_days': max_days,
        'priority': priority,
    }


@router.get('/api/route')
def route_list(
    route_date: str = '', collector_id: Optional[int] = None,
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    user = current_user(authorization, s)
    collector = collector_or_403(s, user, collector_id)
    d = parse_date(route_date, 'data da rota', optional=True) or date.today()
    stops = s.query(CollectorRouteStop).filter_by(collector_id=collector.id, route_date=d).order_by(
        CollectorRouteStop.position, CollectorRouteStop.id
    ).all()
    return {
        'collector': {'id': collector.id, 'name': collector.name},
        'date': str(d),
        'stops': [stop_dict(s, x) for x in stops],
    }


@router.post('/api/route/generate')
def generate_route(
    route_date: str = Form(''), collector_id: Optional[int] = Form(None),
    authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    user = current_user(authorization, s)
    collector = collector_or_403(s, user, collector_id)
    d = parse_date(route_date, 'data da rota', optional=True) or date.today()

    due = s.query(Installment).join(Contract).filter(
        Contract.collector_id == collector.id,
        Installment.status != 'paid',
        Installment.due_date <= d,
    ).all()
    client_ids = []
    seen = set()
    scored = []
    for item in due:
        contract = s.get(Contract, item.contract_id)
        if not contract or contract.client_id in seen:
            continue
        seen.add(contract.client_id)
        pending, due_today, overdue, max_days = client_pending_snapshot(s, collector.id, contract.client_id, d)
        score = max_days * 1000 + overdue * 2 + due_today
        scored.append((score, contract.client_id))
    scored.sort(reverse=True)
    client_ids = [cid for _, cid in scored]

    existing = {x.client_id for x in s.query(CollectorRouteStop).filter_by(collector_id=collector.id, route_date=d).all()}
    position = s.query(func.max(CollectorRouteStop.position)).filter_by(collector_id=collector.id, route_date=d).scalar() or 0
    created = 0
    for cid in client_ids:
        if cid in existing:
            continue
        position += 1
        s.add(CollectorRouteStop(collector_id=collector.id, client_id=cid, route_date=d, position=position))
        created += 1
    s.commit()
    log(s, user, 'ROUTE_GENERATE', f'{collector.id}:{d}:{created}')
    return {'ok': True, 'created': created}


@router.post('/api/route/add')
def route_add(
    client_id: int = Form(...), route_date: str = Form(''), collector_id: Optional[int] = Form(None),
    scheduled_time: str = Form(''), note: str = Form(''), authorization: Optional[str] = Header(None),
    s: Session = Depends(db)
):
    user = current_user(authorization, s)
    collector = collector_or_403(s, user, collector_id)
    d = parse_date(route_date, 'data da rota', optional=True) or date.today()
    client = s.get(Client, client_id)
    if not client or client.collector_id != collector.id:
        raise HTTPException(400, 'Cliente não pertence à carteira deste cobrador')
    exists = s.query(CollectorRouteStop).filter_by(collector_id=collector.id, client_id=client_id, route_date=d).first()
    if exists:
        raise HTTPException(409, 'Cliente já está na rota deste dia')
    position = (s.query(func.max(CollectorRouteStop.position)).filter_by(collector_id=collector.id, route_date=d).scalar() or 0) + 1
    stop = CollectorRouteStop(
        collector_id=collector.id, client_id=client_id, route_date=d, position=position,
        scheduled_time=scheduled_time[:5], note=note,
    )
    s.add(stop); s.commit(); s.refresh(stop)
    log(s, user, 'ROUTE_ADD', f'{collector.id}:{client_id}:{d}')
    return stop_dict(s, stop)


@router.patch('/api/route/{stop_id}')
def route_update(
    stop_id: int, status: str = Form(''), note: str = Form(''), position: Optional[int] = Form(None),
    scheduled_time: str = Form(''), authorization: Optional[str] = Header(None), s: Session = Depends(db)
):
    user = current_user(authorization, s)
    stop = s.get(CollectorRouteStop, stop_id)
    if not stop:
        raise HTTPException(404, 'Parada não encontrada')
    if user.role != 'admin' and stop.collector_id != user.id:
        raise HTTPException(403, 'Rota fora da sua carteira')
    if status:
        if status not in ('pending', 'visited', 'paid', 'rescheduled', 'skipped'):
            raise HTTPException(400, 'Status inválido')
        stop.status = status
    if note != '':
        stop.note = note
    if position is not None and position > 0:
        stop.position = position
    if scheduled_time != '':
        stop.scheduled_time = scheduled_time[:5]
    s.commit()
    log(s, user, 'ROUTE_UPDATE', f'{stop_id}:{stop.status}')
    return stop_dict(s, stop)


@router.get('/api/analytics/delinquency')
def delinquency(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    user = current_user(authorization, s)
    today_ = date.today()
    iq = s.query(Installment).join(Contract).filter(Installment.status != 'paid')
    if user.role != 'admin':
        iq = iq.filter(Contract.collector_id == user.id)
    pending_items = iq.all()
    overdue_items = [i for i in pending_items if i.due_date < today_]

    overdue_total = sum(max(0, i.amount - i.paid_amount) for i in overdue_items)
    receivable_total = sum(max(0, i.amount - i.paid_amount) for i in pending_items)
    aging_defs = [('1–7 dias', 1, 7), ('8–15 dias', 8, 15), ('16–30 dias', 16, 30), ('31–60 dias', 31, 60), ('60+ dias', 61, 100000)]
    aging = []
    for label, lo, hi in aging_defs:
        selected = [i for i in overdue_items if lo <= (today_ - i.due_date).days <= hi]
        aging.append({
            'label': label,
            'count': len(selected),
            'amount': sum(max(0, i.amount - i.paid_amount) for i in selected),
        })

    forecast = []
    for days in (7, 15, 30):
        limit = today_ + timedelta(days=days)
        amount = sum(max(0, i.amount - i.paid_amount) for i in pending_items if today_ <= i.due_date <= limit)
        forecast.append({'days': days, 'amount': amount})

    daily = []
    for offset in range(0, 14):
        d = today_ + timedelta(days=offset)
        amount = sum(max(0, i.amount - i.paid_amount) for i in pending_items if i.due_date == d)
        daily.append({'date': str(d), 'amount': amount})

    monthly_receipts = []
    cursor = date(today_.year, today_.month, 1)
    for back in range(5, -1, -1):
        y = cursor.year
        m = cursor.month - back
        while m <= 0:
            y -= 1; m += 12
        start = date(y, m, 1)
        end = date(y, m, monthrange(y, m)[1])
        pq = s.query(Payment).filter(Payment.payment_date >= start, Payment.payment_date <= end)
        if user.role != 'admin':
            pq = pq.filter(Payment.collector_id == user.id)
        amount = sum(p.amount for p in pq.all())
        monthly_receipts.append({'month': start.strftime('%m/%Y'), 'amount': amount})

    collectors = []
    if user.role == 'admin':
        for collector in s.query(User).filter_by(role='collector').order_by(User.name).all():
            items = s.query(Installment).join(Contract).filter(
                Contract.collector_id == collector.id,
                Installment.status != 'paid',
                Installment.due_date < today_,
            ).all()
            amount = sum(max(0, i.amount - i.paid_amount) for i in items)
            collectors.append({'id': collector.id, 'name': collector.name, 'count': len(items), 'amount': amount})
        collectors.sort(key=lambda x: x['amount'], reverse=True)

    delinquency_rate = round((overdue_total / receivable_total * 100), 1) if receivable_total > 0 else 0
    return {
        'receivable_total': receivable_total,
        'overdue_total': overdue_total,
        'overdue_count': len(overdue_items),
        'delinquency_rate': delinquency_rate,
        'aging': aging,
        'forecast': forecast,
        'daily_forecast': daily,
        'monthly_receipts': monthly_receipts,
        'collectors': collectors,
    }
