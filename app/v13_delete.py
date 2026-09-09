from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Header
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.v12_models import (
    Client, Contract, Installment, Payment, Cash, ClientAttachment
)
from app.v12_helpers import db, current_user, require_admin, log
from app.v12_growth import CollectorRouteStop

router = APIRouter()


@router.delete('/api/contracts/{contract_id}')
def delete_contract(
    contract_id: int,
    confirmation: str = Form(...),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    user = current_user(authorization, s)
    require_admin(user)
    contract = s.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, 'Contrato não encontrado')

    expected = f'EXCLUIR {contract.number}'
    if confirmation.strip().upper() != expected.upper():
        raise HTTPException(400, f'Confirmação inválida. Digite: {expected}')

    client_id = contract.client_id
    contract_number = contract.number
    installments = s.query(Installment).filter_by(contract_id=contract.id).all()
    installment_ids = [i.id for i in installments]

    # Remove os movimentos financeiros ligados ao contrato e às parcelas,
    # restaurando o caixa ao estado anterior à criação do contrato.
    refs = [contract_number] + [f'INST-{iid}' for iid in installment_ids] + [f'ESTORNO-INST-{iid}' for iid in installment_ids]
    if refs:
        cash_rows = s.query(Cash).filter(
            or_(
                Cash.reference_id.in_(refs),
                Cash.description.like(f'{contract_number}%'),
            )
        ).all()
        for row in cash_rows:
            s.delete(row)

    for payment in s.query(Payment).filter_by(contract_id=contract.id).all():
        s.delete(payment)
    for item in installments:
        s.delete(item)
    s.delete(contract)
    s.flush()

    # Se o cliente ficou sem qualquer contrato, remove paradas antigas da rota
    # que não fazem mais sentido operacionalmente.
    if s.query(Contract).filter_by(client_id=client_id).count() == 0:
        for stop in s.query(CollectorRouteStop).filter_by(client_id=client_id).all():
            s.delete(stop)

    s.commit()
    log(s, user, 'CONTRACT_DELETE', f'id={contract_id};number={contract_number};client_id={client_id}')
    return {'ok': True, 'contract_id': contract_id, 'number': contract_number}


@router.delete('/api/clients/{client_id}')
def delete_client(
    client_id: int,
    confirmation: str = Form(...),
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    user = current_user(authorization, s)
    require_admin(user)
    client = s.get(Client, client_id)
    if not client:
        raise HTTPException(404, 'Cliente não encontrado')

    contracts_count = s.query(Contract).filter_by(client_id=client.id).count()
    if contracts_count > 0:
        raise HTTPException(
            409,
            f'Este cliente possui {contracts_count} contrato(s). Exclua os contratos primeiro para preservar a integridade financeira.'
        )

    expected = f'EXCLUIR {client.name}'
    if confirmation.strip().upper() != expected.upper():
        raise HTTPException(400, f'Confirmação inválida. Digite: {expected}')

    client_name = client.name
    for attachment in s.query(ClientAttachment).filter_by(client_id=client.id).all():
        s.delete(attachment)
    for stop in s.query(CollectorRouteStop).filter_by(client_id=client.id).all():
        s.delete(stop)
    s.delete(client)
    s.commit()
    log(s, user, 'CLIENT_DELETE', f'id={client_id};name={client_name}')
    return {'ok': True, 'client_id': client_id, 'name': client_name}
