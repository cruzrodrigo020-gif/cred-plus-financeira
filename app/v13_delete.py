from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
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
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    user = current_user(authorization, s)
    require_admin(user)
    contract = s.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, 'Contrato não encontrado')

    client_id = contract.client_id
    contract_number = contract.number
    installment_ids = [
        row[0] for row in s.query(Installment.id).filter(Installment.contract_id == contract_id).all()
    ]

    refs = [contract_number]
    refs += [f'INST-{iid}' for iid in installment_ids]
    refs += [f'ESTORNO-INST-{iid}' for iid in installment_ids]

    # Exclusão explícita em ordem de dependência para respeitar as FKs do PostgreSQL.
    # 1) movimentos financeiros ligados ao contrato/parcela
    if refs:
        s.query(Cash).filter(
            or_(
                Cash.reference_id.in_(refs),
                Cash.description.like(f'{contract_number}%'),
            )
        ).delete(synchronize_session=False)

    # 2) pagamentos apontam para parcelas e contrato
    s.query(Payment).filter(Payment.contract_id == contract_id).delete(synchronize_session=False)

    # 3) parcelas apontam para o contrato
    s.query(Installment).filter(Installment.contract_id == contract_id).delete(synchronize_session=False)

    # 4) só então o contrato pode ser removido
    deleted = s.query(Contract).filter(Contract.id == contract_id).delete(synchronize_session=False)
    if not deleted:
        s.rollback()
        raise HTTPException(404, 'Contrato não encontrado')

    # Se o cliente ficou sem contratos, remove paradas de rota que ficaram sem finalidade.
    remaining_contracts = s.query(Contract).filter(Contract.client_id == client_id).count()
    if remaining_contracts == 0:
        s.query(CollectorRouteStop).filter(
            CollectorRouteStop.client_id == client_id
        ).delete(synchronize_session=False)

    s.commit()
    log(s, user, 'CONTRACT_DELETE', f'id={contract_id};number={contract_number};client_id={client_id}')
    return {'ok': True, 'contract_id': contract_id, 'number': contract_number}


@router.delete('/api/clients/{client_id}')
def delete_client(
    client_id: int,
    authorization: Optional[str] = Header(None),
    s: Session = Depends(db),
):
    user = current_user(authorization, s)
    require_admin(user)
    client = s.get(Client, client_id)
    if not client:
        raise HTTPException(404, 'Cliente não encontrado')

    contracts_count = s.query(Contract).filter(Contract.client_id == client_id).count()
    if contracts_count > 0:
        raise HTTPException(
            409,
            f'Este cliente possui {contracts_count} contrato(s). Exclua os contratos primeiro.'
        )

    client_name = client.name

    # Limpa dependências diretas do cliente antes de apagar a ficha.
    s.query(ClientAttachment).filter(
        ClientAttachment.client_id == client_id
    ).delete(synchronize_session=False)
    s.query(CollectorRouteStop).filter(
        CollectorRouteStop.client_id == client_id
    ).delete(synchronize_session=False)

    deleted = s.query(Client).filter(Client.id == client_id).delete(synchronize_session=False)
    if not deleted:
        s.rollback()
        raise HTTPException(404, 'Cliente não encontrado')

    s.commit()
    log(s, user, 'CLIENT_DELETE', f'id={client_id};name={client_name}')
    return {'ok': True, 'client_id': client_id, 'name': client_name}
