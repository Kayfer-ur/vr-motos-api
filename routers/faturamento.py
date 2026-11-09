from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_usuario_atual, requer_admin
from database import get_db
from models import FaturamentoMensal
from schemas import FaturamentoEntrada, FaturamentoSaida

router = APIRouter(prefix="/faturamento", tags=["Faturamento"])


@router.get("", response_model=list[FaturamentoSaida])
def listar_faturamentos(db: Session = Depends(get_db), _usuario: dict = Depends(get_usuario_atual)):
    """Devolve os valores de faturamento informados por ciclo (Mês VR)."""
    registros = db.query(FaturamentoMensal).all()
    return [{"mes": f.mes, "valor": float(f.valor)} for f in registros]


@router.put("", response_model=FaturamentoSaida, dependencies=[Depends(requer_admin)])
def salvar_faturamento(dados: FaturamentoEntrada, db: Session = Depends(get_db)):
    """Cria ou atualiza o valor de faturamento de um ciclo. Exclusivo para admin."""
    registro = db.query(FaturamentoMensal).filter_by(mes=dados.mes).first()
    if registro is None:
        registro = FaturamentoMensal(mes=dados.mes, valor=dados.valor)
        db.add(registro)
    else:
        registro.valor = dados.valor
    db.commit()
    db.refresh(registro)
    return {"mes": registro.mes, "valor": float(registro.valor)}
