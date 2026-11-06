from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="investidor")  # admin | investidor


class Moto(Base):
    __tablename__ = "motos"

    id = Column(Integer, primary_key=True, index=True)
    marca = Column(String(80), nullable=False)
    modelo = Column(String(120), nullable=False)
    ano = Column(Integer, nullable=False)
    cor = Column(String(60), nullable=False)
    preco = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), nullable=False, default="DISPONIVEL")  # DISPONIVEL | VENDIDA
    # Guarda o caminho relativo da foto principal (a 1ª enviada).
    imagem_url = Column(String(255), nullable=True)
    data_cadastro = Column(DateTime, nullable=False, default=datetime.utcnow)
    data_venda = Column(DateTime, nullable=True)

    fotos = relationship(
        "Foto",
        back_populates="moto",
        cascade="all, delete-orphan",
        order_by="Foto.id",
    )


class Foto(Base):
    __tablename__ = "fotos"

    id = Column(Integer, primary_key=True, index=True)
    moto_id = Column(Integer, ForeignKey("motos.id"), nullable=False, index=True)
    caminho = Column(String(255), nullable=False)  # ex.: "static/fotos/abc123.jpg"

    moto = relationship("Moto", back_populates="fotos")
