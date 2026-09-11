from app.v12 import app
from app.v12_models import SessionLocal, Client, Audit
from app import v14_public

RETRY_ACTION = 'WHATSAPP_CONFIRM_RETRY_ONCE'
RETRY_CLIENT_ID = 4


@app.on_event('startup')
def retry_failed_whatsapp_confirmation_once():
    s = SessionLocal()
    try:
        already = s.query(Audit).filter_by(action=RETRY_ACTION).first()
        if already:
            return
        client = s.get(Client, RETRY_CLIENT_ID)
        if not client:
            s.add(Audit(user_id=None, action=RETRY_ACTION, details=f'client_id={RETRY_CLIENT_ID};not_found'))
            s.commit()
            return
        v14_public.send_whatsapp_confirmation(client.id, client.name, client.whatsapp)
        s.add(Audit(user_id=None, action=RETRY_ACTION, details=f'client_id={client.id};attempted'))
        s.commit()
    except Exception as exc:
        s.rollback()
        print(f'PUBLIC_CONFIRM_WHATSAPP_RETRY_ERROR client_id={RETRY_CLIENT_ID} error={type(exc).__name__}')
    finally:
        s.close()
