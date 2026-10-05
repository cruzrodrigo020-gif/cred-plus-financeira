from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.v12_models import (
    Client, Contract, Installment, Payment, ClientAttachment
)
from app.v12_helpers import db, current_user, require_admin, log
from app.v12_growth import CollectorRouteStop
from app.v22_delinquency import ContractLateFeeRule

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

    installments = s.query(Installment).filter(Installment.contract_id == contract_id).all()
    if not installments:
        raise HTTPException(409, 'Este contrato não possui parcelas e não pode ser excluído por esta opção.')

    balance = round(sum(max(0, float(i.amount or 0) - float(i.paid_amount or 0)) for i in installments), 2)
    fully_paid = balance <= 0.005 and all(
        i.status == 'paid' or float(i.paid_amount or 0) >= float(i.amount or 0) - 0.005
        for i in installments
    )
    if not fully_paid:
        raise HTTPException(
            409,
            f'Somente contratos totalmente pagos podem ser excluídos. Saldo atual: R$ {balance:.2f}'.replace('.', ',')
        )

    client_id = contract.client_id
    contract_number = contract.number

    # Mantém os movimentos de caixa já registrados para preservar o histórico financeiro.
    # Remove apenas registros que possuem FK direta para o contrato.
    s.query(ContractLateFeeRule).filter(
        ContractLateFeeRule.contract_id == contract_id
    ).delete(synchronize_session=False)

    s.query(Payment).filter(
        Payment.contract_id == contract_id
    ).delete(synchronize_session=False)

    s.query(Installment).filter(
        Installment.contract_id == contract_id
    ).delete(synchronize_session=False)

    deleted = s.query(Contract).filter(
        Contract.id == contract_id
    ).delete(synchronize_session=False)
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
    log(
        s,
        user,
        'PAID_CONTRACT_DELETE',
        f'id={contract_id};number={contract_number};client_id={client_id};cash_history=preserved'
    )
    return {
        'ok': True,
        'contract_id': contract_id,
        'number': contract_number,
        'cash_history_preserved': True,
    }


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
