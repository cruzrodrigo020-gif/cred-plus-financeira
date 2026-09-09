# CRED+ Financeira V10

Versão com **backend FastAPI + SQLAlchemy + banco SQL + painel web**.

## Rodar localmente

1. Instale Python 3.11+.
2. No diretório do projeto:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

3. Abra `http://127.0.0.1:8000`.

## Acesso inicial
Em produção, o usuário e a senha do administrador são definidos pelas variáveis `ADMIN_USERNAME` e `ADMIN_PASSWORD`. Nenhuma senha real deve ser versionada no repositório.

## Banco
Por padrão usa SQLite (`credplus.db`). O projeto está estruturado com SQLAlchemy para migrar para PostgreSQL usando `DATABASE_URL`.

## API
A documentação interativa fica em `/docs`.

## Segurança e produção
Esta é uma base funcional para desenvolvimento. Para produção, configure SECRET_KEY forte, HTTPS, PostgreSQL, migrations (Alembic), backup automático, rate limiting, logs, políticas de senha, recuperação de acesso e autorização no servidor. Revise juridicamente os produtos, taxas, cobranças e contratos antes de operar comercialmente.

## Produção

Defina `DATABASE_URL`, `SECRET_KEY`, `ADMIN_USERNAME` e `ADMIN_PASSWORD` como variáveis de ambiente. Em PostgreSQL, a aplicação normaliza automaticamente `postgresql://` para o driver `psycopg`. O health check é `GET /health`.
