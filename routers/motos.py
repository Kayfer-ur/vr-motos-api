import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from auth import requer_admin
from database import get_db
from models import Foto, Moto
from schemas import MotoSaida

router = APIRouter(prefix="/motos", tags=["Motos"])

# Pasta local onde as fotos são guardadas (raiz do projeto / static / fotos)
PASTA_FOTOS = Path(__file__).resolve().parent.parent / "static" / "fotos"
PASTA_FOTOS.mkdir(parents=True, exist_ok=True)

STATUS_VALIDOS = {"DISPONIVEL", "VENDIDA"}


def _url_completa(request: Request, caminho_relativo: Optional[str]) -> Optional[str]:
    """Converte 'static/fotos/abc.jpg' em 'http://127.0.0.1:8000/static/fotos/abc.jpg'."""
    if not caminho_relativo:
        return None
    return f"{str(request.base_url).rstrip('/')}/{caminho_relativo}"


def _ciclo_vr(data_venda: Optional[datetime]) -> Optional[str]:
    """Deriva o ciclo 'Mês VR' (21 do mês anterior a 20 do mês) da data de venda.

    Ex.: 21/10 a 20/11 -> "11"; 21/11 a 20/12 -> "12". Usado pelo filtro do Dashboard.
    """
    if data_venda is None:
        return None
    if data_venda.day >= 21:
        return str(data_venda.month % 12 + 1)
    return str(data_venda.month)


def _montar_saida(moto: Moto, request: Request) -> MotoSaida:
    urls = [u for u in (_url_completa(request, f.caminho) for f in moto.fotos) if u]

    # Compatibilidade: motos antigas que só têm imagem_url (cadastro com uma única foto)
    if not urls and moto.imagem_url:
        u = _url_completa(request, moto.imagem_url)
        urls = [u] if u else []

    return MotoSaida(
        id=moto.id,
        marca=moto.marca,
        modelo=moto.modelo,
        ano=moto.ano,
        cor=moto.cor,
        preco=float(moto.preco),
        status=moto.status,
        imagem_url=urls[0] if urls else None,
        fotos=urls,
        ciclo=_ciclo_vr(moto.data_venda),
        data_cadastro=moto.data_cadastro.strftime("%Y-%m-%d %H:%M") if moto.data_cadastro else None,
        data_venda=moto.data_venda.strftime("%Y-%m-%d %H:%M") if moto.data_venda else None,
    )


def _guardar_foto(imagem: UploadFile) -> str:
    """Grava o ficheiro em static/fotos/ e devolve o caminho relativo a guardar na BD."""
    if imagem.content_type and not imagem.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="O ficheiro enviado não é uma imagem.")

    extensao = Path(imagem.filename or "").suffix.lower()
    if extensao not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        extensao = ".jpg"

    nome = f"{uuid.uuid4().hex}{extensao}"
    caminho = PASTA_FOTOS / nome
    caminho.write_bytes(imagem.file.read())
    return f"static/fotos/{nome}"


@router.get("", response_model=list[MotoSaida])
def listar_motos(request: Request, db: Session = Depends(get_db)):
    """Lista todas as motos com URLs prontas para o <img> do HTML e cálculo do Dashboard."""
    motos = db.query(Moto).order_by(Moto.id.desc()).all()
    return [_montar_saida(m, request) for m in motos]


@router.post("", response_model=MotoSaida, status_code=201, dependencies=[Depends(requer_admin)])
def cadastrar_moto(
    request: Request,
    marca: str = Form(...),
    modelo: str = Form(...),
    ano: int = Form(...),
    cor: str = Form(...),
    preco: Decimal = Form(...),
    status: str = Form("DISPONIVEL"),
    data_venda: Optional[date] = Form(None),
    imagens: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Cadastro via FormData (multipart), com uma ou mais fotos."""
    status = status.upper()
    if status not in STATUS_VALIDOS:
        raise HTTPException(status_code=400, detail="Status deve ser DISPONIVEL ou VENDIDA.")

    if not imagens:
        raise HTTPException(status_code=400, detail="Envie pelo menos uma foto.")

    caminhos = [_guardar_foto(img) for img in imagens]

    moto = Moto(
        marca=marca,
        modelo=modelo,
        ano=ano,
        cor=cor,
        preco=preco,
        status=status,
        imagem_url=caminhos[0],
        data_venda=datetime.combine(data_venda, datetime.min.time()) if data_venda else None,
        fotos=[Foto(caminho=c) for c in caminhos],
    )
    db.add(moto)
    db.commit()
    db.refresh(moto)
    return _montar_saida(moto, request)


@router.patch("/{moto_id}/vender", response_model=MotoSaida, dependencies=[Depends(requer_admin)])
def vender_moto(moto_id: int, request: Request, db: Session = Depends(get_db)):
    """Marca a moto como VENDIDA e grava a data_venda (alimenta o Dashboard do front-end)."""
    moto = db.query(Moto).filter(Moto.id == moto_id).first()
    if moto is None:
        raise HTTPException(status_code=404, detail="Moto não encontrada.")

    moto.status = "VENDIDA"
    if moto.data_venda is None:
        moto.data_venda = datetime.utcnow()
    db.commit()
    db.refresh(moto)
    return _montar_saida(moto, request)


@router.delete("/{moto_id}", dependencies=[Depends(requer_admin)])
def apagar_moto(moto_id: int, db: Session = Depends(get_db)):
    """Apaga a moto e as suas fotos (ficheiros no disco + registos na BD)."""
    moto = db.query(Moto).filter(Moto.id == moto_id).first()
    if moto is None:
        raise HTTPException(status_code=404, detail="Moto não encontrada.")

    # Apaga os ficheiros de imagem do disco
    for foto in list(moto.fotos):
        caminho_abs = PASTA_FOTOS / Path(foto.caminho).name
        try:
            if caminho_abs.exists():
                caminho_abs.unlink()
        except OSError:
            pass

    db.delete(moto)  # o cascade apaga as linhas da tabela 'fotos'
    db.commit()
    return {"ok": True, "detail": "Moto apagada."}
