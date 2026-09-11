import os
import time

os.environ.setdefault('TZ', 'America/Belem')
if hasattr(time, 'tzset'):
    time.tzset()

from fastapi.responses import FileResponse

from app.v12 import app
from app.v12_growth import router as growth_router
from app.v13_whatsapp import router as whatsapp_router
from app.v13_delete import router as delete_router
from app.v14_public import router as public_router
from app import v14_whatsapp_debug  # ativa diagnóstico seguro de falhas da API do WhatsApp
from app.v15_lender import router as lender_router

app.title = 'CRED+ Financeira Premium'
app.version = '12.8.1'
app.include_router(growth_router)
app.include_router(whatsapp_router)
app.include_router(delete_router)
app.include_router(public_router)
app.include_router(lender_router)


@app.get('/cobrador')
def collector_app():
    return FileResponse('app/static/collector.html')


@app.get('/cobrador/')
def collector_app_slash():
    return FileResponse('app/static/collector.html')


@app.get('/cadastro')
def public_register():
    return FileResponse('app/static/public-register.html')


@app.get('/cadastro/')
def public_register_slash():
    return FileResponse('app/static/public-register.html')


@app.get('/emprestador')
def lender_app():
    return FileResponse('app/static/lender.html')


@app.get('/emprestador/')
def lender_app_slash():
    return FileResponse('app/static/lender.html')


@app.get('/emprestador/cadastro')
def lender_register():
    return FileResponse('app/static/lender-register.html')


@app.get('/emprestador/cadastro/')
def lender_register_slash():
    return FileResponse('app/static/lender-register.html')
