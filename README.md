# 🌳 IpêLMS — mini-AVA em Flask + SQLite

IpêLMS é um **mini Ambiente Virtual de Aprendizagem** (tipo “Aprender3”) criado do zero com **Flask**, **Jinja** e **SQLite** (sem ORM, sem WTForms), focado em didática e simplicidade.

> **Stack**: Python 3.11+ (ok em 3.13), Flask, Jinja, sqlite3 (stdlib).  
> **SO alvo**: Linux Manjaro (mas roda em qualquer Linux/macOS/WSL).  
> **Sem libs extras**: nada de ORM/WTForms/Bootstrap.

---

## 📦 Recursos (MVP)

1. **Autenticação**
   - Registro, login, logout.
   - Hash de senha com `werkzeug.security`.
   - Sessão com chave secreta.
   - **CSRF caseiro** (token armazenado na sessão).

2. **Cursos & matrículas**
   - Criar/listar curso.
   - Aluno entra/sai do curso.
   - **Dashboard** do aluno/instrutor.

3. **Aulas (módulos)**
   - CRUD por instrutores.
   - Exibição para alunos.
   - Upload de **anexo** (até 10 MB; tipos básicos).

4. **Avisos do curso**
   - Mural simples: instrutor publica; alunos leem.

5. **Tarefas & notas**
   - Instrutor cria tarefa.
   - Aluno envia **texto e/ou arquivo**.
   - Instrutor lança **nota** e **feedback**.
   - **Boletim** do aluno.

6. **Páginas/UX**
   - Layout base Jinja, navbar, flashes.
   - CSS leve próprio, responsivo.

7. **Banco & Migrações**
   - `sqlite3` + `migrations/*.sql`.
   - CLI: `flask db-status|db-upgrade|db-history|db-baseline|db-verify`.

8. **Segurança básica**
   - CSRF caseiro, **rate limit** simples (login/registro).
   - Tamanho máximo de upload.
   - Validações de campos (limites).
   - Headers de segurança (CSP, XFO, HSTS em produção).
   - Rotas protegidas com `@login_required`.

9. **Logs**
   - `logs/app.log` (eventos).
   - `logs/access.log` (um por requisição, **X-Request-ID**, tempo).

---

## 🗂️ Estrutura de pastas

```
ipelms-project/
  ├── ipelms/
  │   ├── app.py                # app factory, logging, headers, CLI migrações
  │   ├── db.py                 # conexão/queries SQLite
  │   ├── migrate.py            # comandos de migração (Flask CLI)
  │   ├── auth.py               # registro/login/logout + injeções no template
  │   ├── courses.py            # cursos + matrícula
  │   ├── lessons.py            # aulas + anexos
  │   ├── notices.py            # mural de avisos
  │   ├── assignments.py        # tarefas, envios, notas, boletim
  │   ├── security.py           # CSRF, login_required, rate_limit
  │   ├── models.sql            # snapshot do schema atual
  │   ├── templates/
  │   │   ├── base.html
  │   │   ├── index.html
  │   │   ├── auth/...
  │   │   ├── courses/...
  │   │   ├── lessons/...
  │   │   ├── notices/...
  │   │   └── assignments/...
  │   └── static/
  │       └── style.css
  ├── migrations/
  │   ├── 0001_initial.sql
  │   └── 0002_due_date_and_more_indexes.sql
  ├── config/
  │   ├── config.json           # {"site_name": "...", "environment": "development|production"}
  │   └── secret_key.txt        # >= 32 chars
  ├── uploads/                  # anexos (criado automaticamente)
  ├── logs/                     # app.log / access.log
  ├── data.db                   # banco SQLite (gerado após rodar)
  ├── .env.example              # variáveis úteis do Flask CLI
  └── README.md
```

---

## 🚀 Quickstart (Manjaro)

### 1) Pré-requisitos

```bash
sudo pacman -Syu python python-pip sqlite
```

### 2) Ambiente virtual + Flask

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install flask
```

### 3) Configuração mínima

```bash
mkdir -p config logs uploads instance

# Crie a secret (>= 32 chars)
python - <<'PY'
import secrets, sys
print(secrets.token_urlsafe(48))
PY > config/secret_key.txt

# Nome do site e ambiente
cat > config/config.json <<'JSON'
{ "site_name": "IpêLMS", "environment": "development" }
JSON
```

> **Produção local**: troque `"environment"` para `"production"` em `config.json` (ativa `SESSION_COOKIE_SECURE` e adiciona HSTS).

### 4) Banco de dados — migrações

- **Novo banco** (recomendado):

```bash
flask --app ipelms.app db-status
flask --app ipelms.app db-upgrade     # aplica 0001 e 0002
flask --app ipelms.app db-history
```

- **Banco existente** (já tinha tabelas): marque baseline e aplique só o que faltar.

```bash
flask --app ipelms.app db-baseline --to 0001
flask --app ipelms.app db-upgrade
```

### 5) Rodar o servidor

```bash
# Opção A (recomendada): modo debug via CLI
flask --app ipelms.app run --debug

# Opção B: python -m (equivalente)
python -m ipelms.app
```

Acesse: <http://127.0.0.1:5000/>

---

## 👤 Usuários, papéis e matrículas

- **Papéis (`users.role`)**: `student` (padrão), `instructor`, `admin` (a lógica atual usa `student`/`instructor`).
- Para virar **instrutor**: adicione entrada em `course_instructors` do curso (ao criar curso, o autor já vira instrutor daquele curso).  
  Ex.: promover usuário `u` a instrutor do curso `c`:
  ```sql
  INSERT OR IGNORE INTO course_instructors(course_id, user_id) VALUES (c, u);
  ```
- **Matrícula de aluno**: a própria UI permite **Entrar no curso** / **Sair do curso**.

---

## 📚 Funcionalidades — visão rápida

- **Cursos:** criar (título, código único), listar, detalhar (aulas, avisos, tarefas, instrutores, nº de alunos).  
- **Aulas:** instrutor cria/edita/exclui; anexo opcional (10 MB máx). Alunos visualizam.  
- **Avisos:** instrutor publica; alunos leem.  
- **Tarefas:** instrutor cria; aluno envia texto/arquivo; instrutor lança nota/feedback; boletim por curso.

---

## 🛡️ Segurança

- **CSRF**: token na sessão (`security.get_csrf_token()`), validado em `POST/PUT/PATCH/DELETE`.
- **Rate limit**: simples em memória, aplicado em `/auth/login` e `/auth/register`.  
  - Ex.: `@rate_limit(max_requests=8, window_seconds=60)` no login.
- **Headers**: `CSP`, `X-Frame-Options=DENY`, `X-Content-Type-Options=nosniff`, `Referrer-Policy=strict-origin-when-cross-origin`, `Permissions-Policy`. `HSTS` só em **production**.
- **Uploads**: até **10 MB** (`MAX_CONTENT_LENGTH`), extensões permitidas nas blueprints.
- **Autorização**: rotas protegidas com `@login_required`; verificações de **instrutor** vs **aluno** em cada recurso.

> **Importante:** projeto educacional; **não use em produção real** sem uma revisão de segurança mais profunda.

---

## 🧭 Rotas principais (exemplos)

- **Home**: `GET /`
- **Healthcheck**: `GET /healthz` (retorna JSON)
- **Auth**:
  - `GET /auth/register` (form) → `POST /auth/register`
  - `GET /auth/login` (form) → `POST /auth/login`
  - `GET /auth/logout`
- **Cursos**:
  - `GET /courses/` (lista), `GET /courses/new`, `POST /courses/`
  - `GET /courses/<id>` (detalhe)
  - `POST /courses/<id>/join` e `POST /courses/<id>/leave`
- **Aulas**:
  - `GET /lessons/new/<course_id>`, `POST /lessons/create/<course_id>`
  - `GET /lessons/<id>`, `GET /lessons/<id>/edit`, `POST /lessons/<id>/edit`, `POST /lessons/<id>/delete`
  - `GET /lessons/download/<id>`
- **Avisos**:
  - `GET /notices/new/<int:course_id>`, `POST /notices/create/<int:course_id>`
  - `GET /notices/<int:notice_id>`
- **Tarefas**:
  - `GET /assignments/new/<int:course_id>`, `POST /assignments/create/<int:course_id>`
  - `GET /assignments/<int:assignment_id>`
  - `POST /assignments/<int:assignment_id>/submit`
  - `POST /assignments/<int:assignment_id>/grade/<int:student_id>`
  - `GET /assignments/grades/<int:course_id>` (boletim do usuário logado)

---

## 🧩 Migrações (CLI)

- **Ver status**: `flask --app ipelms.app db-status`
- **Aplicar**: `flask --app ipelms.app db-upgrade`
- **Histórico**: `flask --app ipelms.app db-history`
- **Baseline** (marcar versão como aplicada sem rodar SQL):  
  `flask --app ipelms.app db-baseline --to 0001`
- **Integridade**: `flask --app ipelms.app db-verify`

Os arquivos SQL estão em `migrations/`. O snapshot do schema atual está em `ipelms/models.sql`.

---

## 🪵 Logs

- **Aplicação**: `logs/app.log` — eventos (curso criado, upload, etc.).  
- **Acesso**: `logs/access.log` — uma linha por requisição no formato tipo *combined* + `rt=X.XXms` + `req_id=...`.  
- Cada resposta retorna **`X-Request-ID`** para correlação.

Exemplos:
```bash
tail -n 30 logs/access.log
tail -n 30 logs/app.log
```

---

## 🧪 Testes rápidos com `curl` + `sqlite3`

> Os exemplos abaixo assumem o servidor em `http://127.0.0.1:5000`.

### 1) Criar conta e login

```bash
# 1. Abrir login para capturar CSRF
curl -s -c cookies.txt "http://127.0.0.1:5000/auth/register" -o r.html
RTOKEN=$(sed -n 's/.*name="csrf_token" value="\([^"]*\)".*/\1/p' r.html)

# 2. Registrar
curl -i -b cookies.txt -c cookies.txt -X POST   -d "csrf_token=$RTOKEN&name=Ana Silva&email=ana@example.com&password=senha123"   "http://127.0.0.1:5000/auth/register"

# 3. Login
curl -s -b cookies.txt "http://127.0.0.1:5000/auth/login" -o l.html
LTOKEN=$(sed -n 's/.*name="csrf_token" value="\([^"]*\)".*/\1/p' l.html)
curl -i -b cookies.txt -c cookies.txt -X POST   -d "csrf_token=$LTOKEN&email=ana@example.com&password=senha123"   "http://127.0.0.1:5000/auth/login"
```

### 2) Criar curso e virar instrutor do próprio curso

```bash
# Form para CSRF
curl -s -b cookies.txt "http://127.0.0.1:5000/courses/new" -o c.html
CTOKEN=$(sed -n 's/.*name="csrf_token" value="\([^"]*\)".*/\1/p' c.html)

# Criar curso
curl -i -b cookies.txt -X POST   -d "csrf_token=$CTOKEN&title=Algoritmos 1&description=Introdução&code=ALG1"   "http://127.0.0.1:5000/courses/"
```

### 3) Criar uma aula com anexo

```bash
COURSE_ID=$(sqlite3 data.db "SELECT id FROM courses WHERE code='ALG1';")
curl -s -b cookies.txt "http://127.0.0.1:5000/lessons/new/$COURSE_ID" -o ln.html
LTOKEN=$(sed -n 's/.*name="csrf_token" value="\([^"]*\)".*/\1/p' ln.html)

# Crie um arquivo pequeno
echo "Material de apoio" > apoio.txt

curl -i -b cookies.txt -X POST   -F "csrf_token=$LTOKEN"   -F "title=Aula 1"   -F "content=Apresentação"   -F "attachment=@apoio.txt"   "http://127.0.0.1:5000/lessons/create/$COURSE_ID"
```

### 4) Criar tarefa, enviar e corrigir

```bash
# Nova tarefa (instrutor)
curl -s -b cookies.txt "http://127.0.0.1:5000/assignments/new/$COURSE_ID" -o an.html
ATOKEN=$(sed -n 's/.*name="csrf_token" value="\([^"]*\)".*/\1/p' an.html)
curl -i -b cookies.txt -X POST   -d "csrf_token=$ATOKEN&title=Trabalho 1&description=Ler e resumir."   "http://127.0.0.1:5000/assignments/create/$COURSE_ID"
ASSIGN_ID=$(sqlite3 data.db "SELECT id FROM assignments WHERE course_id=$COURSE_ID ORDER BY id DESC LIMIT 1;")

# Simular aluno: crie outro usuário, matricule no curso pela UI, pegue CSRF e envie.
```

---

## 🧰 `sqlite3` — inspeções úteis

```bash
sqlite3 data.db ".tables"
sqlite3 data.db "PRAGMA table_info(users);"
sqlite3 data.db "SELECT id, email, role FROM users ORDER BY id DESC LIMIT 5;"
sqlite3 data.db "SELECT id, code, title FROM courses ORDER BY id DESC LIMIT 5;"
```

---

## 🗜️ Backup & manutenção do banco

```bash
# Backup "online" seguro (SQLite)
sqlite3 data.db ".backup 'backup-$(date +%F_%H%M).db'"

# VACUUM (compactar)
sqlite3 data.db "VACUUM;"
```

---

## 🧯 Troubleshooting (erros comuns)

- **`KeyError: 'UPLOADS_DIR'` ao iniciar**: garanta que `app.py` está na versão que cria pastas (LOGS/UPLOADS/INSTANCE) e usa `UPLOAD_FOLDER` (já corrigido nos passos 7+).
- **`TypeError: 'NoneType' object is not subscriptable` no `/dashboard`**: sessão órfã. Atualize `security.py` (passo 12/ajuste): `login_required` limpa sessão e redireciona.
- **`413 Request Entity Too Large`**: seu arquivo > 10 MB. Diminua o tamanho.
- **CSRF inválido**: o token mudou (nova aba/tempo). Recarregue o formulário antes de enviar.
- **Rate limit 429** no login/registro: aguarde a janela (configurada no decorator) ou reduza tentativas.

Logs ajudam muito:
```bash
tail -n 80 logs/app.log
tail -n 80 logs/access.log
```

---

## 🔐 Produção local (opcional)

- Coloque `"environment": "production"` no `config/config.json` para forçar cookies `Secure` e HSTS.  
- **Atenção**: isso exige HTTPS real atrás de um reverse proxy. Em desenvolvimento, mantenha `"development"`.

---

## 🤝 Contribuindo

1. Crie um branch: `git checkout -b feat/nome-da-mudanca`
2. Edite/adicione arquivos (siga os padrões deste README).
3. `git add -A && git commit -m "feat: descrição"`
4. `git push` e abra um PR.