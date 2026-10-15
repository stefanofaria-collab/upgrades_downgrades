import pymysql
from pymysql.cursors import DictCursor

from . import config

_BASE = dict(cursorclass=DictCursor, connect_timeout=15, read_timeout=300)


def conectar():
    """Conecta ao MySQL.

    O PyMySQL converte a senha (str) para latin1. Se a senha tem caracteres como
    '£' ou 'ç' e o servidor a guardou em UTF-8, o login é recusado (erro 1045).
    Por isso, se a primeira tentativa falhar com 1045, tentamos de novo enviando
    a senha em UTF-8.
    """
    cfg = dict(config.DB)
    senha = cfg["password"]
    try:
        return pymysql.connect(**cfg, **_BASE)
    except pymysql.err.OperationalError as exc:
        if exc.args[0] != 1045 or senha.isascii():
            raise
    cfg["password"] = senha.encode("utf-8")
    return pymysql.connect(**cfg, **_BASE)


def run_query(sql: str, params: dict | None = None) -> list[dict]:
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            return list(cur.fetchall())
    finally:
        conn.close()
