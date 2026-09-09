import os
from io import BytesIO
from datetime import datetime, timedelta, date
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import FastAPI, Depends, HTTPException, Form, Header, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import (
    create_engine, String, Integer, Float, Date, DateTime, ForeignKey,
    Boolean, Text, LargeBinary, inspect, text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DB = os.getenv('DATABASE_URL', 'sqlite:///./credplus.db')
if DB.startswith('postgresql://'):
    DB = DB.replace('postgresql://', 'postgresql+psycopg://', 1)
SECRET = os.getenv('SECRET_KEY', 'change-me')
ADMIN_USER = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASSWORD', 'admin123')

engine = create_engine(
    DB,
    pool_pre_ping=True,
    connect_args={'check_same_thread': False} if DB.startswith('sqlite') else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
pwd = CryptContext(schemes=['bcrypt'], deprecated='auto')


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default='collector')
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Client(Base):
    __tablename__ = 'clients'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    cpf: Mapped[str] = mapped_column(String(20), default='', index=True)
    rg: Mapped[str] = mapped_column(String(30), default='')
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    whatsapp: Mapped[str] = mapped_column(String(30), default='')
    phone: Mapped[str] = mapped_column(String(30), default='')
    email: Mapped[str] = mapped_column(String(160), default='')
    marital_status: Mapped[str] = mapped_column(String(60), default='')
    profession: Mapped[str] = mapped_column(String(120), default='')
    company: Mapped[str] = mapped_column(String(160), default='')
    time_at_work: Mapped[str] = mapped_column(String(80), default='')
    income: Mapped[float] = mapped_column(Float, default=0)
    address: Mapped[str] = mapped_column(String(255), default='')
    cep: Mapped[str] = mapped_column(String(20), default='')
    street: Mapped[str] = mapped_column(String(180), default='')
    address_number: Mapped[str] = mapped_column(String(30), default='')
    neighborhood: Mapped[str] = mapped_column(String(120), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    state: Mapped[str] = mapped_column(String(40), default='')
    address_reference: Mapped[str] = mapped_column(String(255), default='')
    reference1_name: Mapped[str] = mapped_column(String(160), default='')
    reference1_phone: Mapped[str] = mapped_column(String(40), default='')
    reference2_name: Mapped[str] = mapped_column(String(160), default='')
    reference2_phone: Mapped[str] = mapped_column(String(40), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    collector_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    rate: Mapped[float] = mapped_column(Float)
    days: Mapped[int] = mapped_column(Integer)
    periodicity: Mapped[str] = mapped_column(String(20))


class Contract(Base):
    __tablename__ = 'contracts'
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'))
    principal: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    installments: Mapped[int] = mapped_column(Integer)
    installment_value: Mapped[float] = mapped_column(Float)
    first_due: Mapped[date] = mapped_column(Date)
    rate: Mapped[float] = mapped_column(Float)
    periodicity: Mapped[str] = mapped_column(String(20))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    collector_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Installment(Base):
    __tablename__ = 'installments'
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'))
    number: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    paid_amount: Mapped[float] = mapped_column(Float, default=0)
    paid_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[int] = mapped_column(primary_key=True)
    installment_id: Mapped[int] = mapped_column(ForeignKey('installments.id'))
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'))
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'))
    collector_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    payment_date: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(30), default='PIX')
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cash(Base):
    __tablename__ = 'cash_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(80))
    amount: Mapped[float] = mapped_column(Float)
    movement_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, default='')
    reference_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)


class Closing(Base):
    __tablename__ = 'closings'
    id: Mapped[int] = mapped_column(primary_key=True)
    collector_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    closing_date: Mapped[date] = mapped_column(Date)
    expected: Mapped[float] = mapped_column(Float, default=0)
    received: Mapped[float] = mapped_column(Float, default=0)
    declared: Mapped[float] = mapped_column(Float, default=0)
    difference: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(30), default='closed')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClientAttachment(Base):
    __tablename__ = 'client_attachments'
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'))
    category: Mapped[str] = mapped_column(String(30), default='document')
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default='application/octet-stream')
    size: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Audit(Base):
    __tablename__ = 'audit_log'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


CLIENT_MIGRATIONS = {
    'rg': "VARCHAR(30) DEFAULT ''",
    'birth_date': 'DATE',
    'email': "VARCHAR(160) DEFAULT ''",
    'marital_status': "VARCHAR(60) DEFAULT ''",
    'company': "VARCHAR(160) DEFAULT ''",
    'time_at_work': "VARCHAR(80) DEFAULT ''",
    'cep': "VARCHAR(20) DEFAULT ''",
    'street': "VARCHAR(180) DEFAULT ''",
    'address_number': "VARCHAR(30) DEFAULT ''",
    'neighborhood': "VARCHAR(120) DEFAULT ''",
    'state': "VARCHAR(40) DEFAULT ''",
    'address_reference': "VARCHAR(255) DEFAULT ''",
    'reference1_name': "VARCHAR(160) DEFAULT ''",
    'reference1_phone': "VARCHAR(40) DEFAULT ''",
    'reference2_name': "VARCHAR(160) DEFAULT ''",
    'reference2_phone': "VARCHAR(40) DEFAULT ''",
}


def migrate_schema():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if 'clients' in tables:
        current = {c['name'] for c in inspector.get_columns('clients')}
        with engine.begin() as conn:
            for column, sql_type in CLIENT_MIGRATIONS.items():
                if column not in current:
                    conn.execute(text(f'ALTER TABLE clients ADD COLUMN {column} {sql_type}'))
    if 'cash_movements' in tables:
        current = {c['name'] for c in inspector.get_columns('cash_movements')}
        if 'reference_id' not in current:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE cash_movements ADD COLUMN reference_id VARCHAR(80)'))


migrate_schema()
Base.metadata.create_all(engine)
