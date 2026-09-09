import os
from datetime import datetime, timedelta, date
from typing import Optional
import jwt
from passlib.context import CryptContext
from fastapi import FastAPI, Depends, HTTPException, Form, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, String, Integer, Float, Date, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

DB=os.getenv('DATABASE_URL','sqlite:///./credplus.db')
if DB.startswith('postgresql://'): DB=DB.replace('postgresql://','postgresql+psycopg://',1)
SECRET=os.getenv('SECRET_KEY','change-me')
ADMIN_USER=os.getenv('ADMIN_USERNAME','admin')
ADMIN_PASS=os.getenv('ADMIN_PASSWORD','admin123')
engine=create_engine(DB,pool_pre_ping=True,connect_args={'check_same_thread':False} if DB.startswith('sqlite') else {})
SessionLocal=sessionmaker(bind=engine,autoflush=False,autocommit=False)
pwd=CryptContext(schemes=['bcrypt'],deprecated='auto')

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(120)); username:Mapped[str]=mapped_column(String(80),unique=True,index=True); password_hash:Mapped[str]=mapped_column(String(255)); role:Mapped[str]=mapped_column(String(30),default='collector'); active:Mapped[bool]=mapped_column(Boolean,default=True)
class Client(Base):
    __tablename__='clients'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(160)); cpf:Mapped[str]=mapped_column(String(20),default='',index=True); whatsapp:Mapped[str]=mapped_column(String(30),default=''); phone:Mapped[str]=mapped_column(String(30),default=''); profession:Mapped[str]=mapped_column(String(120),default=''); income:Mapped[float]=mapped_column(Float,default=0); address:Mapped[str]=mapped_column(String(255),default=''); city:Mapped[str]=mapped_column(String(100),default=''); notes:Mapped[str]=mapped_column(Text,default=''); collector_id:Mapped[Optional[int]]=mapped_column(ForeignKey('users.id'),nullable=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Product(Base):
    __tablename__='products'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(120)); rate:Mapped[float]=mapped_column(Float); days:Mapped[int]=mapped_column(Integer); periodicity:Mapped[str]=mapped_column(String(20))
class Contract(Base):
    __tablename__='contracts'; id:Mapped[int]=mapped_column(primary_key=True); number:Mapped[str]=mapped_column(String(40),unique=True); client_id:Mapped[int]=mapped_column(ForeignKey('clients.id')); principal:Mapped[float]=mapped_column(Float); total:Mapped[float]=mapped_column(Float); installments:Mapped[int]=mapped_column(Integer); installment_value:Mapped[float]=mapped_column(Float); first_due:Mapped[date]=mapped_column(Date); rate:Mapped[float]=mapped_column(Float); periodicity:Mapped[str]=mapped_column(String(20)); product_id:Mapped[int]=mapped_column(ForeignKey('products.id')); collector_id:Mapped[Optional[int]]=mapped_column(ForeignKey('users.id'),nullable=True); status:Mapped[str]=mapped_column(String(30),default='active'); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Installment(Base):
    __tablename__='installments'; id:Mapped[int]=mapped_column(primary_key=True); contract_id:Mapped[int]=mapped_column(ForeignKey('contracts.id')); number:Mapped[int]=mapped_column(Integer); due_date:Mapped[date]=mapped_column(Date); amount:Mapped[float]=mapped_column(Float); status:Mapped[str]=mapped_column(String(20),default='pending'); paid_amount:Mapped[float]=mapped_column(Float,default=0); paid_at:Mapped[Optional[date]]=mapped_column(Date,nullable=True)
class Payment(Base):
    __tablename__='payments'; id:Mapped[int]=mapped_column(primary_key=True); installment_id:Mapped[int]=mapped_column(ForeignKey('installments.id')); contract_id:Mapped[int]=mapped_column(ForeignKey('contracts.id')); client_id:Mapped[int]=mapped_column(ForeignKey('clients.id')); collector_id:Mapped[Optional[int]]=mapped_column(ForeignKey('users.id'),nullable=True); amount:Mapped[float]=mapped_column(Float); payment_date:Mapped[date]=mapped_column(Date); method:Mapped[str]=mapped_column(String(30),default='PIX'); note:Mapped[str]=mapped_column(Text,default=''); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Cash(Base):
    __tablename__='cash_movements'; id:Mapped[int]=mapped_column(primary_key=True); kind:Mapped[str]=mapped_column(String(10)); category:Mapped[str]=mapped_column(String(80)); amount:Mapped[float]=mapped_column(Float); movement_date:Mapped[date]=mapped_column(Date); description:Mapped[str]=mapped_column(Text,default=''); user_id:Mapped[Optional[int]]=mapped_column(ForeignKey('users.id'),nullable=True)
class Audit(Base):
    __tablename__='audit_log'; id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[Optional[int]]=mapped_column(ForeignKey('users.id'),nullable=True); action:Mapped[str]=mapped_column(String(80)); details:Mapped[str]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

Base.metadata.create_all(engine)
def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()
def make_token(u): return jwt.encode({'sub':str(u.id),'role':u.role,'exp':datetime.utcnow()+timedelta(hours=8)},SECRET,algorithm='HS256')
def auth(h:Optional[str],s:Session):
    if not h or not h.startswith('Bearer '): raise HTTPException(401,'Não autenticado')
    try: p=jwt.decode(h[7:],SECRET,algorithms=['HS256']); u=s.get(User,int(p['sub']))
    except Exception: raise HTTPException(401,'Token inválido ou expirado')
    if not u or not u.active: raise HTTPException(401,'Usuário inativo')
    return u
def admin(u):
    if u.role!='admin': raise HTTPException(403,'Acesso restrito ao administrador')
def log(s,u,a,d): s.add(Audit(user_id=u.id if u else None,action=a,details=d)); s.commit()

app=FastAPI(title='CRED+ Financeira API',version='10.1.0')
app.mount('/static',StaticFiles(directory='app/static'),name='static')
@app.on_event('startup')
def seed():
    s=SessionLocal()
    if not s.query(User).filter_by(username=ADMIN_USER).first(): s.add(User(name='Administrador',username=ADMIN_USER,password_hash=pwd.hash(ADMIN_PASS),role='admin'))
    if s.query(Product).count()==0: s.add_all([Product(name='Diário • 20 parcelas',rate=20,days=20,periodicity='daily'),Product(name='Final • 20 dias',rate=30,days=20,periodicity='final'),Product(name='Final • 30 dias',rate=35,days=30,periodicity='final')])
    s.commit(); s.close()
@app.get('/health')
def health(): return {'ok':True}
@app.get('/')
def home(): return FileResponse('app/static/index.html')
@app.post('/api/login')
def login(username:str=Form(...),password:str=Form(...),s:Session=Depends(db)):
    u=s.query(User).filter_by(username=username).first()
    if not u or not u.active or not pwd.verify(password,u.password_hash): raise HTTPException(401,'Usuário ou senha inválidos')
    log(s,u,'LOGIN','Acesso realizado'); return {'token':make_token(u),'user':{'id':u.id,'name':u.name,'role':u.role}}
@app.get('/api/me')
def me(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); return {'id':u.id,'name':u.name,'role':u.role}
@app.get('/api/dashboard')
def dashboard(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); today=date.today(); scope=[]
    q=s.query(Installment).join(Contract)
    if u.role=='collector': q=q.filter(Contract.collector_id==u.id)
    scope=q.all(); rec=sum(max(0,i.amount-i.paid_amount) for i in scope if i.status!='paid'); late=sum(max(0,i.amount-i.paid_amount) for i in scope if i.status!='paid' and i.due_date<today)
    pq=s.query(Payment)
    if u.role=='collector': pq=pq.filter(Payment.collector_id==u.id)
    received=sum(p.amount for p in pq.filter(Payment.payment_date==today).all())
    cash_in=sum(x.amount for x in s.query(Cash).filter(Cash.kind=='in').all()); cash_out=sum(x.amount for x in s.query(Cash).filter(Cash.kind=='out').all())
    cq=s.query(Client); kq=s.query(Contract).filter_by(status='active')
    if u.role=='collector': cq=cq.filter(Client.collector_id==u.id); kq=kq.filter(Contract.collector_id==u.id)
    return {'cash':cash_in-cash_out,'receivable':rec,'overdue':late,'received_today':received,'clients':cq.count(),'contracts':kq.count(),'role':u.role}
@app.get('/api/clients')
def clients(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); q=s.query(Client)
    if u.role=='collector': q=q.filter(Client.collector_id==u.id)
    return [{'id':x.id,'name':x.name,'cpf':x.cpf,'whatsapp':x.whatsapp,'profession':x.profession,'income':x.income,'address':x.address,'city':x.city,'collector_id':x.collector_id} for x in q.order_by(Client.name).all()]
@app.post('/api/clients')
def create_client(name:str=Form(...),cpf:str=Form(''),whatsapp:str=Form(''),phone:str=Form(''),profession:str=Form(''),income:float=Form(0),address:str=Form(''),city:str=Form(''),notes:str=Form(''),collector_id:Optional[int]=Form(None),authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); cid=collector_id if u.role=='admin' else u.id; x=Client(name=name,cpf=cpf,whatsapp=whatsapp,phone=phone,profession=profession,income=income,address=address,city=city,notes=notes,collector_id=cid); s.add(x); s.commit(); log(s,u,'CLIENT_CREATE',name); return {'id':x.id}
@app.get('/api/products')
def products(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    auth(authorization,s); return [{'id':x.id,'name':x.name,'rate':x.rate,'days':x.days,'periodicity':x.periodicity} for x in s.query(Product).all()]
@app.get('/api/contracts')
def contracts(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); q=s.query(Contract)
    if u.role=='collector': q=q.filter(Contract.collector_id==u.id)
    return [{'id':x.id,'number':x.number,'client':s.get(Client,x.client_id).name,'principal':x.principal,'total':x.total,'installments':x.installments,'first_due':str(x.first_due),'status':x.status} for x in q.order_by(Contract.id.desc()).all()]
@app.post('/api/contracts')
def create_contract(client_id:int=Form(...),product_id:int=Form(...),principal:float=Form(...),installments:int=Form(...),first_due:str=Form(...),authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); admin(u); p=s.get(Product,product_id); c=s.get(Client,client_id)
    if not p or not c: raise HTTPException(404,'Cliente/produto não encontrado')
    if principal<=0 or installments<=0: raise HTTPException(400,'Valor e parcelas devem ser maiores que zero')
    n=1 if p.periodicity=='final' else installments; total=round(principal*(1+p.rate/100),2); val=round(total/n,2); due=date.fromisoformat(first_due); number='CTR-'+datetime.now().strftime('%y%m%d%H%M%S%f')[-10:]
    x=Contract(number=number,client_id=c.id,principal=principal,total=total,installments=n,installment_value=val,first_due=due,rate=p.rate,periodicity=p.periodicity,product_id=p.id,collector_id=c.collector_id,status='active'); s.add(x); s.flush()
    for i in range(1,n+1): s.add(Installment(contract_id=x.id,number=i,due_date=due+timedelta(days=i-1),amount=val))
    s.add(Cash(kind='out',category='Crédito liberado',amount=principal,movement_date=date.today(),description=number,user_id=u.id)); s.commit(); log(s,u,'CONTRACT_CREATE',number); return {'id':x.id,'number':number}
@app.get('/api/installments')
def installments(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); q=s.query(Installment).join(Contract)
    if u.role=='collector': q=q.filter(Contract.collector_id==u.id)
    out=[]
    for i in q.order_by(Installment.due_date).all():
        c=s.get(Contract,i.contract_id); out.append({'id':i.id,'contract_id':i.contract_id,'contract':c.number,'client':s.get(Client,c.client_id).name,'number':i.number,'due_date':str(i.due_date),'amount':i.amount,'status':i.status,'paid_amount':i.paid_amount})
    return out
@app.patch('/api/installments/{iid}')
def edit_installment(iid:int,due_date:str=Form(...),authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); admin(u); i=s.get(Installment,iid)
    if not i: raise HTTPException(404,'Parcela não encontrada')
    old=i.due_date; i.due_date=date.fromisoformat(due_date); s.commit(); log(s,u,'DUE_DATE_CHANGE',f'{iid}: {old} -> {i.due_date}'); return {'ok':True}
@app.post('/api/payments')
def payment(installment_id:int=Form(...),amount:float=Form(...),payment_date:str=Form(...),method:str=Form('PIX'),note:str=Form(''),authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); i=s.get(Installment,installment_id)
    if not i: raise HTTPException(404,'Parcela não encontrada')
    c=s.get(Contract,i.contract_id)
    if u.role=='collector' and c.collector_id!=u.id: raise HTTPException(403,'Parcela fora da sua carteira')
    remaining=max(0,i.amount-i.paid_amount)
    if amount<=0 or amount>remaining+0.005: raise HTTPException(400,'Valor de pagamento inválido')
    paid=date.fromisoformat(payment_date); i.paid_amount+=amount; i.paid_at=paid; i.status='paid' if i.paid_amount>=i.amount-0.005 else 'partial'; collector=u.id if u.role=='collector' else c.collector_id
    s.add(Payment(installment_id=i.id,contract_id=c.id,client_id=c.client_id,collector_id=collector,amount=amount,payment_date=paid,method=method,note=note)); s.add(Cash(kind='in',category='Pagamento de parcela',amount=amount,movement_date=paid,description=c.number,user_id=u.id)); s.commit(); log(s,u,'PAYMENT_CREATE',f'{c.number}/{i.number}'); return {'ok':True}
@app.post('/api/cash/expense')
def expense(amount:float=Form(...),movement_date:str=Form(...),description:str=Form(''),authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); admin(u)
    if amount<=0: raise HTTPException(400,'Valor inválido')
    s.add(Cash(kind='out',category='Despesa',amount=amount,movement_date=date.fromisoformat(movement_date),description=description,user_id=u.id)); s.commit(); log(s,u,'EXPENSE',str(amount)); return {'ok':True}
@app.get('/api/users')
def users(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); admin(u); return [{'id':x.id,'name':x.name,'username':x.username,'role':x.role,'active':x.active} for x in s.query(User).all()]
@app.post('/api/users')
def create_user(name:str=Form(...),username:str=Form(...),password:str=Form(...),role:str=Form('collector'),authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    u=auth(authorization,s); admin(u)
    if role not in ('admin','collector'): raise HTTPException(400,'Perfil inválido')
    if len(password)<8: raise HTTPException(400,'A senha deve ter pelo menos 8 caracteres')
    if s.query(User).filter_by(username=username).first(): raise HTTPException(409,'Usuário já existe')
    x=User(name=name,username=username,password_hash=pwd.hash(password),role=role); s.add(x); s.commit(); log(s,u,'USER_CREATE',username); return {'id':x.id}
