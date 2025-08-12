# IpêLMS (mini-AVA com Flask)

Stack: Python 3.x, Flask, sqlite3 (stdlib), Jinja, CSS leve.

## Rodando localmente
1) `python -m venv .venv && source .venv/bin/activate`
2) `pip install flask`
3) `flask --app ipelms.app run --debug`

## Estrutura (inicial)
ipelms/
  app.py
  __init__.py
  templates/
    base.html
    index.html
  static/
    style.css
config/
  config.json
  secret_key.txt
logs/
uploads/
tests/