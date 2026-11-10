import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from auth import requer_admin
from database import get_db
from models import Foto, Moto
from schemas import MotoEdicao, MotoSaida


def _configurar_cloudinary():
    """Configura o Cloudinary a partir da variável de ambiente CLOUDINARY_URL."""
    url = os.environ.get("CLOUDINARY_URL", "")
    if url.startswith("cloudinary://"):
        rest = url[len("cloudinary://"):]
        if "@" in rest:
            creds, cloud_name = rest.rsplit("@", 1)
            if ":" in creds:
                api_key, api_secret = creds.split(":", 1)
                cloudinary.config(
                    cloud_name=cloud_name,
                    api_key=api_key,
                    api_secret=api_secret,
                    secure=True,
                )


_configurar_cloudinary()

router = APIRouter(prefix="/motos", tags=["Motos"])

# Pasta local onde as fotos eram guardadas (mantida por compatibilidade)
PASTA_FOTOS = Path(__file__).resolve().parent.parent / "static" / "fotos"
PASTA_FOTOS.mkdir(parents=True, exist_ok=True)

STATUS_VALIDOS = {"Estoque", "Vendido"}

# Lucro fixo por moto vendida
LUCRO_FIXO = Decimal("700")


def _url_completa(request: Request, caminho_relativo: Optional[str]) -> Optional[str]:
    """Converte 'static/fotos/abc.jpg' em URL completa (usado apenas para fotos antigas locais)."""
    if not caminho_relativo:
        return None
    return f"{str(request.base_url).rstrip('/')}/{caminho_relativo}"


def _para_url(caminho: Optional[str], request: Request) -> Optional[str]:
    """Devolve o URL da foto: direto se já for um link (Cloudinary) ou local."""
    if not caminho:
        return None
    if caminho.startswith("http"):
        return caminho
    return _url_completa(request, caminho)


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
    urls = [u for u in (_para_url(f.caminho, request) for f in moto.fotos) if u]

    # Compatibilidade: motos antigas que só têm imagem_url (cadastro com uma única foto)
    if not urls and moto.imagem_url:
        u = _para_url(moto.imagem_url, request)
        urls = [u] if u else []

    return MotoSaida(
        id=moto.id,
        marca=moto.marca,
        modelo=moto.modelo,
        ano=moto.ano,
        cor=moto.cor,
        chassi=moto.chassi,
        preco=float(moto.preco),
        status=moto.status,
        imagem_url=urls[0] if urls else None,
        fotos=urls,
        ciclo=_ciclo_vr(moto.data_venda),
        data_cadastro=moto.data_cadastro.strftime("%Y-%m-%d %H:%M") if moto.data_cadastro else None,
        data_venda=moto.data_venda.strftime("%Y-%m-%d %H:%M") if moto.data_venda else None,
    )


def _guardar_foto(imagem: UploadFile) -> str:
    """Envia a foto para o Cloudinary e devolve o URL seguro (guardado na BD)."""
    if imagem.content_type and not imagem.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="O ficheiro enviado não é uma imagem.")

    imagem.file.seek(0)
    try:
        resultado = cloudinary.uploader.upload(
            imagem.file,
            public_id=f"{uuid.uuid4().hex}",
            resource_type="image",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao enviar a foto: {e}")
    return resultado.get("secure_url") or resultado.get("url")


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
    chassi: Optional[str] = Form(None),
    preco: Decimal = Form(...),
    status: str = Form("Estoque"),
    data_venda: Optional[date] = Form(None),
    imagens: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Cadastro via FormData (multipart), com uma ou mais fotos."""
    if status not in STATUS_VALIDOS:
        raise HTTPException(status_code=400, detail="Status deve ser Estoque ou Vendido.")

    if not imagens:
        raise HTTPException(status_code=400, detail="Envie pelo menos uma foto.")

    caminhos = [_guardar_foto(img) for img in imagens]

    # Custo calculado silenciosamente: preço menos o lucro fixo de R$ 700
    preco_custo = preco - LUCRO_FIXO

    moto = Moto(
        marca=marca,
        modelo=modelo,
        ano=ano,
        cor=cor,
        chassi=chassi,
        preco=preco,
        preco_custo=preco_custo,
        status=status,
        imagem_url=caminhos[0],
        data_venda=datetime.combine(data_venda, datetime.min.time()) if data_venda else None,
        fotos=[Foto(caminho=c) for c in caminhos],
    )
    db.add(moto)
    db.commit()
    db.refresh(moto)
    return _montar_saida(moto, request)


@router.patch("/{moto_id}", response_model=MotoSaida, dependencies=[Depends(requer_admin)])
def editar_moto(moto_id: int, dados: MotoEdicao, request: Request, db: Session = Depends(get_db)):
    """Edita apenas Nome (modelo), Chassi e Valor. Exclusivo para admin."""
    moto = db.query(Moto).filter(Moto.id == moto_id).first()
    if moto is None:
        raise HTTPException(status_code=404, detail="Moto não encontrada.")

    if dados.modelo is not None:
        moto.modelo = dados.modelo
    if dados.chassi is not None:
        moto.chassi = dados.chassi
    if dados.preco is not None:
        moto.preco = Decimal(str(dados.preco))
        moto.preco_custo = moto.preco - LUCRO_FIXO

    db.commit()
    db.refresh(moto)
    return _montar_saida(moto, request)


@router.patch("/{moto_id}/vender", response_model=MotoSaida, dependencies=[Depends(requer_admin)])
def vender_moto(moto_id: int, request: Request, db: Session = Depends(get_db)):
    """Marca a moto como Vendido e grava a data_venda (alimenta o Dashboard do front-end)."""
    moto = db.query(Moto).filter(Moto.id == moto_id).first()
    if moto is None:
        raise HTTPException(status_code=404, detail="Moto não encontrada.")

    moto.status = "Vendido"
    if moto.data_venda is None:
        moto.data_venda = datetime.utcnow()
    db.commit()
    db.refresh(moto)
    return _montar_saida(moto, request)


@router.delete("/{moto_id}", dependencies=[Depends(requer_admin)])
def apagar_moto(moto_id: int, db: Session = Depends(get_db)):
    """Apaga a moto e as suas fotos (Cloudinary e/ou disco) e os registos na BD."""
    moto = db.query(Moto).filter(Moto.id == moto_id).first()
    if moto is None:
        raise HTTPException(status_code=404, detail="Moto não encontrada.")

    for foto in list(moto.fotos):
        if foto.caminho and foto.caminho.startswith("http"):
            # Foto no Cloudinary: apaga pelo public_id (nome sem extensão)
            public_id = Path(foto.caminho).stem
            try:
                cloudinary.uploader.destroy(public_id)
            except Exception:
                pass
        else:
            # Foto local antiga
            caminho_abs = PASTA_FOTOS / Path(foto.caminho).name
            try:
                if caminho_abs.exists():
                    caminho_abs.unlink()
            except OSError:
                pass

    db.delete(moto)  # o cascade apaga as linhas da tabela 'fotos'
    db.commit()
    return {"ok": True, "detail": "Moto apagada."}
