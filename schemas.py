from typing import List, Optional

from pydantic import BaseModel, EmailStr


# ---------- Autenticação ----------
class LoginEntrada(BaseModel):
    email: EmailStr
    senha: str


class UsuarioSaida(BaseModel):
    nome: str
    email: str
    role: str


class LoginSaida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioSaida


# ---------- Motos ----------
class MotoSaida(BaseModel):
    id: int
    marca: str
    modelo: str
    ano: int
    cor: str
    chassi: Optional[str] = None
    preco: float
    status: str
    # URL completa e pronta a usar em <img src="...">
    imagem_url: Optional[str]
    nota_fiscal_url: Optional[str] = None
    fotos: List[str] = []
    # Ciclo "Mês VR" derivado de data_venda (usado no filtro do Dashboard)
    ciclo: Optional[str] = None
    data_cadastro: Optional[str] = None
    data_venda: Optional[str] = None


# ---------- Edição de motos (admin) ----------
class MotoEdicao(BaseModel):
    modelo: Optional[str] = None
    chassi: Optional[str] = None
    preco: Optional[float] = None
