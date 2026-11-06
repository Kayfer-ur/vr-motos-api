from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import criar_token, verificar_senha
from database import get_db
from models import Usuario
from schemas import LoginEntrada, LoginSaida, UsuarioSaida

router = APIRouter(tags=["Autenticação"])


@router.post("/login", response_model=LoginSaida)
def login(dados: LoginEntrada, db: Session = Depends(get_db)):
    """Recebe JSON {email, senha} e devolve o token + dados do utilizador."""
    usuario = db.query(Usuario).filter(Usuario.email == dados.email.lower()).first()

    if usuario is None or not verificar_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Acesso permitido apenas a "admin" ou "investidor".',
        )

    return LoginSaida(
        access_token=criar_token(usuario.email, usuario.role),
        usuario=UsuarioSaida(
            nome=usuario.nome, email=usuario.email, role=usuario.role
        ),
    )
