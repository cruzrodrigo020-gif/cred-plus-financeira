from app.v12 import app
from app.v12_growth import router as growth_router
from app.v13_whatsapp import router as whatsapp_router
from app.v13_delete import router as delete_router

app.title = 'CRED+ Financeira Premium'
app.version = '12.5.0'
app.include_router(growth_router)
app.include_router(whatsapp_router)
app.include_router(delete_router)
