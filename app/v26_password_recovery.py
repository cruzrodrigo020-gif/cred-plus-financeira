import hmac
import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app.v12_helpers import db
from app.v12_models import ADMIN_USER, User, pwd

router = APIRouter()
_attempts = defaultdict(list)
_guard = Lock()


@router.post('/api/password-recovery')
def password_recovery(
    request: Request,
    username: str = Form(...),
    recovery_code: str = Form(''),
    current_password: str = Form(''),
    new_password: str = Form(...),
    s: Session = Depends(db),
):
    # A password must never be reset just by knowing a username.
    ip = request.client.host if request.client else 'unknown'
    key = (ip, username.lower().strip())
    now = time.monotonic()
    with _guard:
        recent = [t for t in _attempts[key] if now - t < 900]
        if len(recent) >= 5:
            raise HTTPException(429, 'Muitas tentativas. Aguarde 15 minutos.')
        recent.append(now)
        _attempts[key] = recent

    if len(new_password) < 12 or len(new_password) > 128:
        raise HTTPException(400, 'Use uma nova senha entre 12 e 128 caracteres.')
    if not any(ch.isalpha() for ch in new_password) or not any(ch.isdigit() for ch in new_password):
        raise HTTPException(400, 'Inclua letras e números na nova senha.')

    user = s.query(User).filter_by(username=username.strip()).first()
    valid_current = bool(user and current_password and pwd.verify(current_password, user.password_hash))
    # Recovery requires an operator-created high-entropy secret in Railway variables.
    configured_code = os.getenv('ADMIN_RECOVERY_CODE', '')
    valid_recovery = bool(
        user and user.role == 'admin' and user.username == ADMIN_USER
        and len(configured_code) >= 20 and recovery_code
        and hmac.compare_digest(configured_code, recovery_code)
    )
    if not (valid_current or valid_recovery):
        raise HTTPException(403, 'Não foi possível confirmar sua identidade. Confira a senha atual ou o código de recuperação configurado no Railway.')
    if pwd.verify(new_password, user.password_hash):
        raise HTTPException(400, 'Escolha uma senha diferente da atual.')
    user.password_hash = pwd.hash(new_password)
    s.commit()
    return {'ok': True, 'message': 'Senha redefinida. Entre com a nova senha.'}
