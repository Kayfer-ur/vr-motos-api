import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth import get_usuario_atual
from database import get_db
from models import Moto

router = APIRouter(tags=["Exportação"])


def _ciclo(data_venda):
    """Mesma regra do 'Mês VR': dia >= 21 pertence ao ciclo (mês) seguinte."""
    if data_venda is None:
        return None
    if data_venda.day >= 21:
        return str(data_venda.month % 12 + 1)
    return str(data_venda.month)


@router.get("/exportar")
def exportar_relatorio(
    mes: str = Query(..., description="Mês VR (ex.: 11 ou 12)"),
    db: Session = Depends(get_db),
    _usuario: dict = Depends(get_usuario_atual),
):
    """Gera um CSV com as motos vendidas no ciclo (Mês VR) selecionado e os lucros."""
    motos = db.query(Moto).filter(Moto.status == "VENDIDA").all()
    vendidas = [m for m in motos if _ciclo(m.data_venda) == mes]

    saida = io.StringIO()
    writer = csv.writer(saida)
    writer.writerow(["Marca", "Modelo", "Ano", "Chassi", "Preço", "Lucro", "Data da Venda"])

    total_preco = 0.0
    total_lucro = 0.0
    for m in vendidas:
        lucro = (m.preco - m.preco_custo) if (m.preco is not None and m.preco_custo is not None) else 700
        total_preco += float(m.preco or 0)
        total_lucro += float(lucro or 0)
        writer.writerow([
            m.marca,
            m.modelo,
            m.ano,
            m.chassi or "",
            f"{float(m.preco or 0):.2f}",
            f"{float(lucro or 0):.2f}",
            m.data_venda.strftime("%d/%m/%Y %H:%M") if m.data_venda else "",
        ])

    writer.writerow([])
    writer.writerow(["TOTAL", "", "", "", f"{total_preco:.2f}", f"{total_lucro:.2f}", f"{len(vendidas)} moto(s)"])

    content = saida.getvalue()
    saida.close()

    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=relatorio_mes_{mes}.csv"},
    )
