from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy import DateTime, ForeignKey, Integer, Text

from app.v12_models import Base, User, engine
from app.v12_helpers import db, current_user

router = APIRouter()


class ChatMessage(Base):
    __tablename__ = 'chat_messages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Base.metadata.create_all(engine)


def _me(authorization: Optional[str], s: Session) -> User:
    return current_user(authorization, s)


def _peer_allowed(me: User, peer: User) -> bool:
    if not peer or not peer.active or peer.id == me.id:
        return False
    if me.role == 'admin':
        return peer.role == 'collector'
    if me.role == 'collector':
        return peer.role == 'admin'
    return False


def _message_dict(m: ChatMessage):
    return {
        'id': m.id,
        'sender_id': m.sender_id,
        'recipient_id': m.recipient_id,
        'message': m.message,
        'created_at': (m.created_at.isoformat() + 'Z') if m.created_at else '',
        'read_at': (m.read_at.isoformat() + 'Z') if m.read_at else '',
    }


@router.get('/api/chat/contacts')
def chat_contacts(
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    me = _me(authorization, s)
    if me.role not in ('admin', 'collector'):
        raise HTTPException(403, 'Chat não disponível para este perfil.')

    role = 'collector' if me.role == 'admin' else 'admin'
    users = s.query(User).filter(User.role == role, User.active.is_(True)).order_by(User.name.asc()).all()
    out = []
    for peer in users:
        last = (
            s.query(ChatMessage)
            .filter(
                or_(
                    and_(ChatMessage.sender_id == me.id, ChatMessage.recipient_id == peer.id),
                    and_(ChatMessage.sender_id == peer.id, ChatMessage.recipient_id == me.id),
                )
            )
            .order_by(ChatMessage.id.desc())
            .first()
        )
        unread = (
            s.query(ChatMessage)
            .filter(
                ChatMessage.sender_id == peer.id,
                ChatMessage.recipient_id == me.id,
                ChatMessage.read_at.is_(None),
            )
            .count()
        )
        out.append({
            'id': peer.id,
            'name': peer.name,
            'role': peer.role,
            'unread': unread,
            'last_message': last.message[:120] if last else '',
            'last_at': (last.created_at.isoformat() + 'Z') if last and last.created_at else '',
        })

    out.sort(key=lambda x: (x['last_at'] or '', x['name'].lower()), reverse=True)
    return out


@router.get('/api/chat/messages/{peer_id}')
def chat_messages(
    peer_id: int,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    me = _me(authorization, s)
    peer = s.get(User, peer_id)
    if not _peer_allowed(me, peer):
        raise HTTPException(403, 'Conversa não permitida.')

    rows = (
        s.query(ChatMessage)
        .filter(
            or_(
                and_(ChatMessage.sender_id == me.id, ChatMessage.recipient_id == peer.id),
                and_(ChatMessage.sender_id == peer.id, ChatMessage.recipient_id == me.id),
            )
        )
        .order_by(ChatMessage.id.desc())
        .limit(250)
        .all()
    )
    rows.reverse()

    now = datetime.utcnow()
    changed = False
    for row in rows:
        if row.recipient_id == me.id and row.read_at is None:
            row.read_at = now
            changed = True
    if changed:
        s.commit()

    return {
        'peer': {'id': peer.id, 'name': peer.name, 'role': peer.role},
        'messages': [_message_dict(m) for m in rows],
    }


@router.post('/api/chat/messages')
def chat_send(
    recipient_id: int = Form(...),
    message: str = Form(...),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    me = _me(authorization, s)
    peer = s.get(User, recipient_id)
    if not _peer_allowed(me, peer):
        raise HTTPException(403, 'Destinatário não permitido.')

    text = (message or '').strip()
    if not text:
        raise HTTPException(400, 'Digite uma mensagem.')
    if len(text) > 2000:
        raise HTTPException(400, 'A mensagem deve ter no máximo 2.000 caracteres.')

    row = ChatMessage(sender_id=me.id, recipient_id=peer.id, message=text)
    s.add(row)
    s.commit()
    s.refresh(row)
    return _message_dict(row)


@router.get('/api/chat/unread')
def chat_unread(
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    me = _me(authorization, s)
    if me.role not in ('admin', 'collector'):
        return {'count': 0}
    count = (
        s.query(ChatMessage)
        .join(User, User.id == ChatMessage.sender_id)
        .filter(
            ChatMessage.recipient_id == me.id,
            ChatMessage.read_at.is_(None),
            User.active.is_(True),
        )
        .count()
    )
    return {'count': count}
