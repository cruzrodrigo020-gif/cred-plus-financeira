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

app.title = 'CRED+ Financeira Premium'
app.version = '12.6.1'
app.include_router(growth_router)
app.include_router(whatsapp_router)
app.include_router(delete_router)


@app.get('/cobrador')
def collector_app():
    return FileResponse('app/static/collector.html')


@app.get('/cobrador/')
def collector_app_slash():
    return FileResponse('app/static/collector.html')
