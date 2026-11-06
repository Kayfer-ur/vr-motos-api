# VR MoTos — API (FastAPI + PostgreSQL)

API limpa e simples, construída exclusivamente para servir o front-end
(`index.html` no Live Server, porta 5500).

## Estrutura

```
vr-motos-api/
├── main.py               # App FastAPI: CORS, /static e routers
├── database.py           # Ligação ao PostgreSQL (lê o .env)
├── models.py             # Tabelas: usuarios e motos
├── schemas.py            # Formatos de entrada/saída (Pydantic)
├── auth.py               # Hash de senha, JWT e dependência de autenticação
├── criar_usuarios.py     # Cria os utilizadores admin e investidor
├── .env                  # Configuração (URL da base, SECRET_KEY)
├── requirements.txt
├── routers/
│   ├── login.py          # POST /login
│   └── motos.py          # GET/POST /motos, PATCH /motos/{id}/vender
└── static/fotos/         # Imagens enviadas no cadastro (servidas em /static)
```

## Arranque (passo a passo)

1. Criar a base de dados no PostgreSQL (uma vez):
   ```bash
   createdb vrmotos     # ou: CREATE DATABASE vrmotos; no psql
   ```
2. Instalar as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Ajustar o `.env` (utilizador/palavra-passe do teu PostgreSQL e uma SECRET_KEY longa).
4. Criar os utilizadores (também cria as tabelas na primeira execução):
   ```bash
   python criar_usuarios.py
   ```
5. Lançar o servidor:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

O front-end (Live Server em `http://127.0.0.1:5500`) fala com a API em
`http://127.0.0.1:8000`. Documentação interativa: `http://127.0.0.1:8000/docs`.

## Utilizadores criados

| Email | Senha | Role |
| --- | --- | --- |
| admin@vrmotos.com | admin123 | admin (pode cadastrar/vender motos) |
| investidor@vrmotos.com | investidor123 | investidor (apenas consulta) |

## Endpoints

| Método | Rota | Auth | Descrição |
| --- | --- | --- | --- |
| POST | `/login` | — | JSON `{email, senha}` → `{access_token, usuario:{nome, role}}` |
| GET | `/motos` | — | Lista de motos com `imagem_url` completa (pronta para `<img>`) |
| POST | `/motos` | admin | **FormData** com os campos + `imagem` (ficheiro); grava a foto em `static/fotos/` |
| PATCH | `/motos/{id}/vender` | admin | Marca como VENDIDA e grava `data_venda` |
| GET | `/static/fotos/...` | — | Serve as imagens gravadas |

## Notas sobre o contrato com o front-end

- `GET /motos` devolve, além dos campos da tabela, `fotos` (lista de URLs, para o
  carrossel) e `ciclo` (string "11"/"12", derivado de `data_venda` pela regra do
  "Mês VR": dia ≥ 21 pertence ao ciclo seguinte) — exatamente o que o Dashboard
  e a tabela do `index.html` esperam.
- `POST /motos` aceita `data_venda` (opcional, `YYYY-MM-DD`) para motos já
  cadastradas como VENDIDas; caso contrário usa `PATCH /vender` mais tarde.
- As senhas são guardadas com hash (pbkdf2_sha256); nunca em texto simples.
