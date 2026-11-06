import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

# pbkdf2_sha256: hash seguro e sem dependências externas problemáticas
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "troca-esta-chave")
EXPIRA_TOKEN_HORAS = int(os.getenv("EXPIRA_TOKEN_HORAS", "8"))

# Esquema usado pelo Swagger; aceita "Authorization: Bearer <token>"
seguranca = HTTPBearer(auto_error=False)


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def criar_token(email: str, role: str) -> str:
    payload = {
        "sub": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=EXPIRA_TOKEN_HORAS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def get_usuario_atual(
    credenciais: HTTPAuthorizationCredentials = Depends(seguranca),
) -> dict:
    """Descodifica o token Bearer e devolve {"email": ..., "role": ...}."""
    if credenciais is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não fornecido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credenciais.credentials, SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"email": payload["sub"], "role": payload["role"]}


def requer_admin(usuario: dict = Depends(get_usuario_atual)) -> dict:
    """Dependência para rotas restritas ao papel 'admin'."""
    if usuario["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso permitido apenas a administradores.",
        )
    return usuario
