from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from auth import hash_senha
from database import Base, SessionLocal, engine
from models import Usuario
import routers.exportar
import routers.login
import routers.motos
import routers.relatorio

# Cria as tabelas na primeira execução (não altera tabelas já existentes)
Base.metadata.create_all(bind=engine)


def _migrar():
    """Migrações idempotentes para tabelas já existentes."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE motos ADD COLUMN IF NOT EXISTS chassi VARCHAR(30)"))
        conn.execute(text("ALTER TABLE motos ADD COLUMN IF NOT EXISTS preco_custo NUMERIC(10,2)"))
        conn.execute(text("ALTER TABLE motos ADD COLUMN IF NOT EXISTS nota_fiscal_url VARCHAR(255)"))
        conn.execute(text("UPDATE motos SET preco_custo = preco - 700 WHERE preco_custo IS NULL"))
        # Conversão dos status antigos para os novos
        conn.execute(text("UPDATE motos SET status = 'Estoque' WHERE status = 'DISPONIVEL'"))
        conn.execute(text("UPDATE motos SET status = 'Vendido' WHERE status = 'VENDIDA'"))


_migrar()


def _criar_usuarios_padrao():
    """Cria os utilizadores iniciais (admin e investidor) se ainda não existirem."""
    padroes = [
        ("Administrador", "admin@vrmotos.com", "admin123", "admin"),
        ("Investidor", "investidor@vrmotos.com", "investidor123", "investidor"),
    ]
    db = SessionLocal()
    try:
        for nome, email, senha, role in padroes:
            if db.query(Usuario).filter_by(email=email).first() is None:
                db.add(Usuario(nome=nome, email=email, senha_hash=hash_senha(senha), role=role))
        db.commit()
    finally:
        db.close()


_criar_usuarios_padrao()

# Raiz do projeto; as fotos ficam sempre em <raiz>/static/fotos/
RAIZ = Path(__file__).resolve().parent

app = FastAPI(title="VR MoTos API", version="1.0.0")

# 1. CORS: liberado para o Live Server (front-end)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",  # variante, caso o Live Server abra com "localhost"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve as fotos guardadas em static/fotos/ (http://127.0.0.1:8000/static/fotos/...)
app.mount("/static", StaticFiles(directory=RAIZ / "static"), name="static")

app.include_router(routers.login.router)
app.include_router(routers.motos.router)
app.include_router(routers.exportar.router)
app.include_router(routers.relatorio.router)


@app.get("/health")
def health():
    return {"status": "ok", "api": "VR MoTos"}


@app.get("/")
def raiz():
    """Serve o front-end (index.html) junto com a API."""
    index = RAIZ / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"status": "ok", "api": "VR MoTos"}
