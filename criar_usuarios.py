"""Cria (ou confirma) os utilizadores 'admin' e 'investidor' na base de dados.

Executar depois de configurar o .env e ter o PostgreSQL a correr:
    python criar_usuarios.py
"""
from database import Base, SessionLocal, engine
import models  # noqa: F401  (garante que as tabelas são conhecidas)
from auth import hash_senha

# (nome, email, senha, role) — altera aqui se quiseres outros valores
UTILIZADORES = [
    ("Administrador", "admin@vrmotos.com", "admin123", "admin"),
    ("Investidor", "investidor@vrmotos.com", "investidor123", "investidor"),
]


def main():
    # Cria as tabelas caso ainda não existam
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for nome, email, senha, role in UTILIZADORES:
            existente = db.query(models.Usuario).filter_by(email=email).first()
            if existente:
                print(f"[=] {email} já existe (role: {existente.role}) — nada feito.")
                continue
            db.add(models.Usuario(nome=nome, email=email, senha_hash=hash_senha(senha), role=role))
            print(f"[+] Criado: {email} / senha: {senha} (role: {role})")
        db.commit()
        print("\nConcluído. Já podes entrar no sistema com estes utilizadores.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
