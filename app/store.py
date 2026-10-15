"""Configurações locais (destinatários e histórico de envios) em SQLite."""
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import config

DB_PATH = config.DATA_DIR / "app.db"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with _conn() as c:
        c.execute(
            "create table if not exists destinatarios ("
            "email text primary key, criado_em text not null)"
        )
        c.execute(
            "create table if not exists envios ("
            "id integer primary key autoincrement, data_ref text not null, "
            "enviado_em text not null, status text not null, destinatarios text, "
            "qtd_upgrades integer, qtd_downgrades integer, saldo integer, erro text)"
        )


def listar_destinatarios() -> list[str]:
    with _conn() as c:
        return [r["email"] for r in c.execute("select email from destinatarios order by email")]


def adicionar_destinatario(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("E-mail inválido")
    with _conn() as c:
        c.execute(
            "insert or ignore into destinatarios(email, criado_em) values (?, ?)",
            (email, datetime.now().isoformat(timespec="seconds")),
        )
    return email


def remover_destinatario(email: str):
    with _conn() as c:
        c.execute("delete from destinatarios where email = ?", (email.strip().lower(),))


def registrar_envio(data_ref, status, destinatarios, ups=0, downs=0, saldo=0, erro=None):
    with _conn() as c:
        c.execute(
            "insert into envios(data_ref, enviado_em, status, destinatarios, qtd_upgrades, "
            "qtd_downgrades, saldo, erro) values (?,?,?,?,?,?,?,?)",
            (str(data_ref), datetime.now().isoformat(timespec="seconds"), status,
             ", ".join(destinatarios) if isinstance(destinatarios, list) else destinatarios,
             ups, downs, saldo, erro),
        )


def ja_enviado(data_ref) -> bool:
    with _conn() as c:
        r = c.execute(
            "select 1 from envios where data_ref = ? and status = 'enviado' limit 1",
            (str(data_ref),),
        ).fetchone()
        return r is not None


def listar_envios(limite: int = 60) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "select * from envios order by id desc limit ?", (limite,))]
