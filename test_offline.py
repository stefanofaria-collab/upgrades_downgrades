"""Teste offline: usa movimentações simuladas (sem acessar o banco nem enviar e-mail)."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import analytics, mailer, scheduler, store
from app.main import app


def ev(i, plano_a, plano_b, dur_a, dur_b, va, vb, dias_atras):
    pago = datetime.combine(analytics.hoje() - timedelta(days=dias_atras), datetime.min.time())
    pesos = {"Bronze": 1, "Prata": 2, "Ouro": 3, "Platina": 4}
    pesod = {"M": 1, "T": 2, "S": 3, "A": 4}
    alt = lambda a, b: "Upgrade" if a > b else ("Downgrade" if a < b else "Sem alteração")
    return {
        "id_plano_atual": i, "empresa_id": 1000 + i, "razao_social": f"Empresa {i} <Ltda> & Cia",
        "plano_anterior": plano_a, "plano_atual": plano_b,
        "alteracao_plano": alt(pesos[plano_b], pesos[plano_a]),
        "duracao_anterior": dur_a, "duracao_atual": dur_b,
        "alteracao_duracao": alt(pesod[dur_b], pesod[dur_a]),
        "valor_anterior": va, "valor_atual": vb, "diferenca_valor": round(vb - va, 2),
        "pagamento_atual": pago, "nome_usuario": "Fulano", "telefone": "3133334444",
        "celular": None, "email": "f@x.com",
    }


rows = [
    ev(1, "Prata", "Bronze", "M", "M", 200, 100, 1),      # downgrade plano (ontem)
    ev(2, "Bronze", "Prata", "M", "M", 100, 200, 1),      # upgrade (ontem)
    ev(3, "Ouro", "Ouro", "A", "M", 1200, 300, 1),        # downgrade duração (ontem)
    ev(4, "Bronze", "Ouro", "A", "M", 900, 700, 1),       # misto, valor cai -> downgrade
    ev(5, "Prata", "Ouro", "M", "M", 200, 300, 40),       # upgrade mês anterior/atual
]
analytics._cache.update(ts=10**12, rows=[analytics._normalizar(r) for r in rows], atualizado_em="x")
# o envio força nova consulta ao banco (force=True); aqui devolvemos os dados simulados
analytics.eventos = lambda force=False: analytics._cache["rows"]

dia = analytics.ontem()
r = analytics.resumo_do_dia(dia)
downs = analytics.downgrades_do_dia(dia)
assert r["upgrades_qtd"] == 1 and r["downgrades_qtd"] == 3 and r["saldo_qtd"] == -2, r
assert [d["empresa_id"] for d in downs] == [1001, 1003, 1004]
csv_txt = mailer.gerar_csv(downs).decode("utf-8-sig")
assert csv_txt.splitlines()[0].count(";") == 15 and "/clientes/visualizar/1001?aba=5" in csv_txt
html = mailer.gerar_html(dia, r, downs)
assert "&lt;Ltda&gt;" in html and "Clientes que fizeram downgrade (3)" in html

store.DB_PATH = store.config.DATA_DIR / "teste.db"
store.DB_PATH.unlink(missing_ok=True)
sent = {}
mailer.enviar = lambda d, a, h, an: sent.update(dests=d, assunto=a, anexos=an)
with TestClient(app) as c:
    o = c.get("/api/overview").json()
    assert o["mensal"][0]["mes"] == "2025-01" and o["cards"]["ontem"]["saldo_qtd"] == -2
    assert c.get("/api/downgrades").json()["itens"][0]["intranet"].endswith("1001?aba=5")
    assert c.post("/api/destinatarios", json={"email": "ruim"}).status_code == 400
    assert c.post("/api/destinatarios", json={"email": "A@b.com"}).json()["destinatarios"] == ["a@b.com"]
    assert c.post("/api/enviar-agora").json()["status"] == "enviado"
    assert sent["dests"] == ["a@b.com"] and sent["anexos"][0][0].endswith(".csv")
    assert scheduler.enviar_relatorio()["status"] == "ignorado"  # já enviado hoje
    assert c.get("/api/envios").json()[0]["status"] == "enviado"
store.DB_PATH.unlink(missing_ok=True)
print("OK", sent["assunto"])
