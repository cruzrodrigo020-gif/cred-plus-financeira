from app.v12 import app
from app.v12_growth import router as growth_router

app.title = 'CRED+ Financeira Premium'
app.version = '12.3.0'
app.include_router(growth_router)
