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
from app.v15_lender import router as lender_router
from app.v16_chat import router as chat_router
from app.v17_payment import router as payment_actions_router
from app.v18_reports import router as reports_router
from app.v19_multi_public import router as multi_public_router
from app.v20_subscriptions import router as subscriptions_router
from app.v22_delinquency import router as delinquency_router

app.title = 'CRED+ Financeira Premium'
app.version = '12.20.0'
app.include_router(growth_router)
app.include_router(whatsapp_router)
app.include_router(delete_router)
app.include_router(public_router)
app.include_router(lender_router)
app.include_router(chat_router)
app.include_router(payment_actions_router)
app.include_router(reports_router)
app.include_router(multi_public_router)
app.include_router(subscriptions_router)
app.include_router(delinquency_router)


@app.middleware('http')
async def no_cache_app_pages(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in ('/', '/cobrador', '/cobrador/', '/cadastro', '/cadastro/', '/painel', '/painel/', '/painel/cadastro', '/painel/cadastro/') or path.startswith('/static/chat-') or path == '/static/chat.css' or path == '/static/v17-payment-actions.js' or path.startswith('/static/public-register.') or path == '/static/v12-core.js' or path == '/static/v12-extra.js' or path == '/static/v12.css' or path == '/static/v13-delete.js' or path == '/static/v18-reports.js' or path.startswith('/static/multi-') or path.startswith('/static/public-multi-client.') or path == '/static/v20-subscriptions.js' or path == '/static/v21-contract-edit.js' or path == '/static/v22-delinquency.js' or path == '/static/v23-installment-order.js' or path.startswith('/painel/cliente/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


def _no_cache_file(path: str):
    return FileResponse(
        path,
        headers={
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
        },
    )


@app.get('/cobrador')
def collector_app():
    return _no_cache_file('app/static/collector.html')


@app.get('/cobrador/')
def collector_app_slash():
    return _no_cache_file('app/static/collector.html')


def _public_register_response():
    return _no_cache_file('app/static/public-register.html')


@app.get('/cadastro')
def public_register():
    return _public_register_response()


@app.get('/cadastro/')
def public_register_slash():
    return _public_register_response()


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


@app.get('/painel')
def multi_admin_app():
    return _no_cache_file('app/static/multi-admin.html')


@app.get('/painel/')
def multi_admin_app_slash():
    return _no_cache_file('app/static/multi-admin.html')


@app.get('/painel/cadastro')
def multi_admin_register():
    return _no_cache_file('app/static/multi-register.html')


@app.get('/painel/cadastro/')
def multi_admin_register_slash():
    return _no_cache_file('app/static/multi-register.html')


@app.get('/painel/cliente/{token}')
def multi_public_client_page(token: str):
    return _no_cache_file('app/static/public-multi-client.html')
