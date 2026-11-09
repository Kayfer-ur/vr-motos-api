# Documentação de Arquitetura — VR MoTos API

> Guia definitivo do projeto **VR MoTos** (sistema de gestão de estoque e vendas de motos).
> Este documento explica a arquitetura do começo ao fim, para que você consiga entender o código e fazer qualquer ajuste manual de forma independente.

---

## 1. Visão Geral e Stack Tecnológico

O projeto é uma aplicação web full-stack dividida em **frontend**, **backend** e **banco de dados**. A comunicação entre as camadas acontece via **HTTP (JSON e FormData)**.

```
┌─────────────────┐        fetch (JSON/FormData)        ┌──────────────────┐        SQLAlchemy         ┌──────────────┐
│    Frontend     │ ──────────────────────────────────▶ │    Backend       │ ────────────────────────▶ │  PostgreSQL  │
│  (index.html)   │ ◀────────────────────────────────── │    (FastAPI)     │ ◀──────────────────────── │   (banco)    │
│ HTML + Tailwind │          JSON (resposta)            │  (Python)        │                            └──────────────┘
│  + JavaScript   │                                     └────────┬─────────┘
└─────────────────┘                                              │  upload de fotos
                                                                 ▼
                                                          ┌──────────────┐
                                                          │  Cloudinary  │
                                                          │ (armazenar   │
                                                          │  imagens)    │
                                                          └──────────────┘
```

### Stack

| Camada | Tecnologia | Papel |
|---|---|---|
| **Frontend** | HTML5 + [Tailwind CSS](https://tailwindcss.com) (via CDN) + JavaScript puro | Interface do usuário. Usa `fetch()` para consumir a API. **Não** usa framework (React/Vue). |
| **Backend** | [FastAPI](https://fastapi.tiangolo.com) (Python) | Servidor HTTP, rotas, validação (Pydantic), autenticação. |
| **Banco** | [PostgreSQL](https://www.postgresql.org) + [SQLAlchemy](https://www.sqlalchemy.org) (ORM) + `psycopg` (driver v3) | Persistência dos dados. |
| **Autenticação** | JWT ([PyJWT](https://pyjwt.readthedocs.io)) + [passlib](https://passlib.readthedocs.io) (`pbkdf2_sha256`) | Login, token Bearer e hash de senha. |
| **Imagens** | [Cloudinary](https://cloudinary.com) | Armazenamento permanente das fotos das motos. |
| **Deploy** | [Render](https://render.com) + [Neon](https://neon.tech) | Hospedagem do backend e banco em produção. |

### Como as camadas se conectam

1. O navegador carrega o `index.html` (servido pelo próprio FastAPI na rota `/`).
2. O JavaScript do frontend faz requisições `fetch()` para a API (`/login`, `/motos`, `/faturamento`, etc.).
3. O FastAPI recebe a requisição, valida os dados (Pydantic) e fala com o PostgreSQL via SQLAlchemy.
4. Quando há upload de foto, o FastAPI envia a imagem para o Cloudinary e guarda no banco apenas a **URL** da imagem.
5. O backend devolve JSON, e o frontend atualiza a tela.

---

## 2. Estrutura de Diretórios

```
vr-motos-api/                      ← raiz do projeto (pasta do deploy)
├── main.py                        ← Ponto de entrada: cria o app FastAPI, CORS, migrações e rotas raiz
├── database.py                    ← Conexão com o PostgreSQL (engine, sessão, Base)
├── models.py                      ← Modelos do banco (tabelas): Usuario, Moto, Foto, FaturamentoMensal
├── schemas.py                     ← Schemas Pydantic (validação de entrada/saída)
├── auth.py                        ← Hash de senha, JWT e dependências de autorização (admin)
├── index.html                     ← Frontend completo (HTML + Tailwind + JavaScript)
├── requirements.txt               ← Dependências Python
├── .env                           ← Variáveis de ambiente (NÃO versionado)
├── render.yaml                    ← Configuração de deploy no Render
├── .gitignore                     ← Arquivos ignorados pelo Git
├── criar_usuarios.py              ← Script auxiliar: cria os usuários admin/investidor
├── criar_banco.py                 ← Script auxiliar: cria o banco de dados local
├── routers/                       ← Rotas da API (endpoints)
│   ├── __init__.py
│   ├── login.py                   ← POST /login (autenticação)
│   ├── motos.py                   ← CRUD de motos (listar, cadastrar, editar, vender, apagar)
│   ├── exportar.py                ← GET /exportar (CSV de vendas)
│   └── faturamento.py             ← GET/PUT /faturamento (valor manual por mês)
└── static/
    └── fotos/                     ← Fotos locais (legado; hoje o padrão é Cloudinary)
```

| Diretório/Arquivo | Responsabilidade |
|---|---|
| `routers/` | Onde ficam **todas as rotas/endpoints** da API. Cada arquivo agrupa um domínio. |
| `models.py` | Define as **tabelas do banco** (classes que viram tabelas via SQLAlchemy). |
| `schemas.py` | Define a **validação e o formato** dos dados (Pydantic). É a "porta" entre HTTP e Python. |
| `index.html` | O **frontend inteiro** num arquivo só (telas + estilos + lógica). |
| `static/fotos/` | Pasta onde imagens locais eram salvas (hoje o Cloudinary é o padrão). |

---

## 3. Modelagem do Banco de Dados (Esquema)

O banco tem **4 tabelas**: `usuarios`, `motos`, `fotos` e `faturamento_mensal`.

### 3.1 `usuarios` (autenticação)

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | Integer (PK) | Identificador único |
| `nome` | String(120) | Nome completo |
| `email` | String(255), unique | E-mail de login |
| `senha_hash` | String(255) | Senha **hasheada** (nunca em texto puro) |
| `role` | String(20) | **`admin`** (gestão total) ou **`investidor`** (só consulta) |

### 3.2 `motos` (estoque e vendas)

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | Integer (PK) | Identificador único |
| `marca` | String(80) | Marca (ex.: Honda) |
| `modelo` | String(120) | Modelo (ex.: CB 500F) |
| `ano` | Integer | Ano do veículo |
| `cor` | String(60) | Cor |
| `chassi` | String(30) | Número do chassi (opcional) |
| `preco` | Numeric(10,2) | Preço de venda |
| `preco_custo` | Numeric(10,2) | **Custo calculado automaticamente** = `preco - 700` |
| `status` | String(20) | **`Estoque`** (disponível) ou **`Vendido`** |
| `imagem_url` | String(255) | URL da foto principal (Cloudinary) |
| `data_cadastro` | DateTime | Data de cadastro |
| `data_venda` | DateTime | Data em que foi vendida (opcional) |

> **Regra de negócio importante:** o lucro é **fixo em R$ 700 por moto**. O `preco_custo` é calculado no backend (`preco - 700`) e **não** é exposto no frontend — o investidor só vê o preço e o ganho.

### 3.3 `fotos` (galeria — 1 moto tem N fotos)

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | Integer (PK) | Identificador único |
| `moto_id` | Integer (FK → `motos.id`) | Qual moto pertence a foto |
| `caminho` | String(255) | URL da imagem (Cloudinary) ou caminho local (legado) |

### 3.4 `faturamento_mensal` (valor manual por mês)

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | Integer (PK) | Identificador único |
| `mes` | String(10), unique | Ciclo "Mês VR" (ex.: `"11"`, `"12"`) |
| `valor` | Numeric(12,2) | Faturamento informado manualmente pelo admin |

### Regra do "Mês VR" (ciclo)

O ciclo é derivado da `data_venda`: **dia ≥ 21 pertence ao mês seguinte**.
- Ex.: 21/10 a 20/11 → ciclo `"11"` (Novembro); 21/11 a 20/12 → ciclo `"12"` (Dezembro).

---

## 4. Mapeamento de Rotas (API Endpoints)

> Legenda de acesso:
> - 🔓 **Público** — sem token.
> - 🔑 **Logado** — qualquer usuário autenticado (admin ou investidor).
> - 👑 **Admin** — somente `role = admin`.

### 4.1 Autenticação (`routers/login.py`)

| Método | URL | Acesso | Descrição |
|---|---|---|---|
| POST | `/login` | 🔓 Público | Recebe `{email, senha}` e devolve `{access_token, token_type, usuario}`. |

### 4.2 Motos (`routers/motos.py`)

| Método | URL | Acesso | Descrição |
|---|---|---|---|
| GET | `/motos` | 🔓 Público | Lista todas as motos (com `fotos` e `ciclo` já calculados). |
| POST | `/motos` | 👑 Admin | Cadastra moto (FormData com 1+ fotos). Calcula `preco_custo = preco - 700`. |
| PATCH | `/motos/{id}` | 👑 Admin | **Edita** só `modelo` (Nome), `chassi` e `preco` (Valor). Recalcula o custo. |
| PATCH | `/motos/{id}/vender` | 👑 Admin | Marca a moto como `Vendido` e grava `data_venda`. |
| DELETE | `/motos/{id}` | 👑 Admin | Apaga a moto e as fotos (banco + Cloudinary). |

### 4.3 Exportação (`routers/exportar.py`)

| Método | URL | Acesso | Descrição |
|---|---|---|---|
| GET | `/exportar?mes={mes}` | 🔑 Logado | Gera e baixa um **CSV** das motos vendidas no ciclo (Mês VR) informado. |

### 4.4 Faturamento manual (`routers/faturamento.py`)

| Método | URL | Acesso | Descrição |
|---|---|---|---|
| GET | `/faturamento` | 🔑 Logado | Lista os valores de faturamento por ciclo. |
| PUT | `/faturamento` | 👑 Admin | Cria/atualiza o faturamento de um ciclo `{mes, valor}`. |

### 4.5 Raiz (`main.py`)

| Método | URL | Acesso | Descrição |
|---|---|---|---|
| GET | `/health` | 🔓 Público | Checagem de saúde do servidor. |
| GET | `/` | 🔓 Público | Serve o `index.html` (o frontend). |

### Como funciona a restrição de acesso

- `get_usuario_atual` (em `auth.py`) decodifica o token `Authorization: Bearer <token>` e devolve `{email, role}`.
- `requer_admin` (em `auth.py`) depende de `get_usuario_atual` e **bloqueia com 403** se `role != "admin"`.
- No frontend, o token fica salvo no `localStorage` e é enviado no header `Authorization` das requisições.

---

## 5. Arquitetura do Frontend

O frontend é um **SPA (Single Page Application) em um único arquivo** `index.html`, com 3 blocos:

1. **HTML** — estrutura das telas e modais.
2. **Tailwind CSS** (via CDN) — estilização, incluindo responsividade mobile (`grid-cols-1 md:grid-cols-2/3`, menu hambúrguer, tabelas com `overflow-x-auto`).
3. **JavaScript** — toda a lógica de interação e chamadas à API.

### 5.1 Telas

| Tela | Elemento | Conteúdo |
|---|---|---|
| **Login** | `#tela-login` | Formulário de e-mail/senha. |
| **Estoque** | `#tela-estoque` | Motos com status `Estoque` (disponíveis). Botão de cadastro (só admin). |
| **Motos Vendidas** | `#tela-vendidas` | Motos com status `Vendido`. |
| **Faturamento** | `#tela-faturamento` | Cards de faturamento + **comparativo Selic** + exportação CSV. |
| **Painel** | `#tela-dashboard` | Capital em estoque ("dinheiro parado") e motos vendidas no ciclo. |

> A troca de telas é feita pela função `mostrarTela(nome)`, que mostra/esconde as divs. Em mobile, o menu vira hambúrguer.

### 5.2 Como o frontend consome a API

O frontend usa **`fetch()` nativo** (sem axios). Padrão típico:

```javascript
const resp = await fetch(API_BASE + "/motos", {
    method: "GET",                                     // ou POST/PATCH/DELETE/PUT
    headers: { "Authorization": "Bearer " + getToken() } // token JWT
    // body: ... (quando necessário)
});
const dados = await resp.json();
```

- `API_BASE` é `""` (relativo), então funciona tanto local quanto em produção (mesmo domínio).
- O token é guardado em `localStorage` (`vrmotos_token`) e o usuário em `vrmotos_user`.
- Funções principais: `fazerLogin`, `carregarMotos`, `cadastrarMoto`, `salvarEdicao`, `venderMoto`, `apagarMoto`, `atualizarFaturamento`, `salvarFaturamento`, `exportarCSV`.

### 5.3 Visão por perfil

| Ação | Admin | Investidor |
|---|---|---|
| Ver estoque, vendidas, faturamento e painel | ✅ | ✅ |
| Cadastrar / Editar / Vender / Apagar moto | ✅ | ❌ (botões nem aparecem) |
| Informar faturamento mensal | ✅ | ❌ |
| Exportar CSV | ✅ | ✅ |

---

## 6. Fluxo de Vida de uma Funcionalidade

### Exemplo 1 — Cadastrar uma moto (com foto)

1. **Admin clica** em "+ Cadastrar Nova" → `abrirModalCadastro()` abre o modal.
2. **Preenche** marca, modelo, ano, cor, chassi, preço, status e seleciona 1+ fotos.
3. **Clica em "Salvar"** → o `onsubmit` chama `cadastrarMoto(event)`.
4. O JS monta um `FormData` com os campos e faz:
   ```javascript
   fetch("/motos", {
       method: "POST",
       headers: { "Authorization": "Bearer " + token },
       body: fd   // multipart com os arquivos
   })
   ```
5. **Backend** (`routers/motos.py` → `cadastrar_moto`):
   - `requer_admin` valida o token e o `role` (se não for admin, retorna 403).
   - Valida o `status` (deve ser `Estoque` ou `Vendido`).
   - Para cada imagem, `_guardar_foto()` envia ao **Cloudinary** e recebe a URL.
   - Calcula `preco_custo = preco - 700`.
   - Cria o registro `Moto` + os registros `Foto` no banco via SQLAlchemy (`db.add`, `db.commit`).
6. O backend devolve o JSON da moto criada.
7. **Frontend** chama `carregarMotos()` → busca `GET /motos` e re-renderiza as tabelas (estoque/vendidas) e os cards.

### Exemplo 2 — Login

1. Usuário digita e-mail/senha e clica em "Entrar".
2. `fazerLogin(event)` faz `POST /login` com `{email, senha}`.
3. Backend (`routers/login.py`) busca o usuário, verifica a senha (passlib) e, se ok, gera um **JWT** (`criar_token`).
4. Frontend salva `access_token` e `usuario` no `localStorage`.
5. A partir daí, toda requisição protegida envia o token no header `Authorization`.

### Exemplo 3 — Editar uma moto (só admin)

1. Admin clica em "✏️ Editar" (o botão **só existe** para admin).
2. `abrirModalEditar(id)` preenche o modal com os dados atuais.
3. Ao salvar, `salvarEdicao(event)` faz `PATCH /motos/{id}` com `{modelo, chassi, preco}`.
4. Backend valida `requer_admin`, atualiza os campos e, se o preço mudou, recalcula `preco_custo`.
5. Frontend recarrega as motos.

---

## 7. Considerações Finais para Manutenção

- **Adicionar uma nova coluna** → edite `models.py`, `schemas.py` (se for exposta) e `routers/motos.py`. Como `create_all` não altera tabelas existentes, adicione a migração em `main.py` → `_migrar()` com `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- **Adicionar uma nova rota** → crie/edite um arquivo em `routers/` e registre em `main.py` com `app.include_router(...)`.
- **Mudar o lucro fixo (R$ 700)** → altere `LUCRO_FIXO` em `routers/motos.py` e o `LUCRO_FIXO` no `index.html`.
- **Mudar a Selic (0,8%) ou o Valor Investido (R$ 90.000)** → altere `SELIC_MENSAL` e `VALOR_INVESTIDO` no `index.html`.
- **Variáveis de ambiente** (`.env` / Render): `DATABASE_URL`, `SECRET_KEY`, `EXPIRA_TOKEN_HORAS`, `CLOUDINARY_URL`.
- **Segurança**: nunca commite o `.env` (já está no `.gitignore`); o `SECRET_KEY` e o `CLOUDINARY_URL` são secretos.
