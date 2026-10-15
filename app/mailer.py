"""Montagem (HTML + CSV) e envio do e-mail diário."""
import csv
import io
import smtplib
from datetime import date
from email.message import EmailMessage
from html import escape

from . import config

COLUNAS_CSV = [
    ("Empresa ID", "empresa_id"),
    ("Razão social", "razao_social"),
    ("Plano anterior", "plano_anterior"),
    ("Plano atual", "plano_atual"),
    ("Alteração do plano", "alteracao_plano"),
    ("Duração anterior", "duracao_anterior_nome"),
    ("Duração atual", "duracao_atual_nome"),
    ("Alteração da duração", "alteracao_duracao"),
    ("Valor anterior", "valor_anterior"),
    ("Valor atual", "valor_atual"),
    ("Saldo financeiro", "diferenca_valor"),
    ("Usuário master", "nome_usuario"),
    ("Telefone", "telefone"),
    ("Celular", "celular"),
    ("E-mail", "email"),
    ("Intranet", None),
]


def brl(v: float) -> str:
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if v < 0 else ''}R$ {s}"


def _data_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _linha(e: dict) -> list:
    out = []
    for _, campo in COLUNAS_CSV:
        out.append(config.INTRANET_URL.format(empresa_id=e["empresa_id"]) if campo is None else e.get(campo))
    return out


def gerar_csv(downs: list[dict]) -> bytes:
    """CSV para Excel BR: separador ';', decimal ',', UTF-8 com BOM."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow([n for n, _ in COLUNAS_CSV])
    for e in downs:
        row = []
        for (nome, _), v in zip(COLUNAS_CSV, _linha(e)):
            if isinstance(v, float):
                v = f"{v:.2f}".replace(".", ",")
            row.append("" if v is None else v)
        w.writerow(row)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _cor(v):  # verde / vermelho
    return "#0a7d4f" if v > 0 else ("#c0123c" if v < 0 else "#334155")


def gerar_html(dia: date, r: dict, downs: list[dict]) -> str:
    saldo = r["saldo_qtd"]
    sinal = f"+{saldo}" if saldo > 0 else str(saldo)

    def card(titulo, valor, sub, cor="#0f2438"):
        return (
            f'<td style="width:25%;padding:6px"><div style="border:1px solid #e2e8f0;border-radius:10px;'
            f'padding:14px;background:#fff"><div style="font-size:11px;letter-spacing:.06em;color:#64748b;'
            f'text-transform:uppercase;font-weight:700">{titulo}</div><div style="font-size:26px;'
            f'font-weight:800;color:{cor};margin-top:6px">{valor}</div>'
            f'<div style="font-size:13px;color:#475569;margin-top:2px">{sub}</div></div></td>'
        )

    cards = (
        card("Saldo do dia", sinal, f"upgrades − downgrades<br>{brl(r['saldo_valor'])}", _cor(saldo))
        + card("Upgrades", r["upgrades_qtd"], brl(r["upgrades_valor"]), "#0a7d4f")
        + card("Downgrades", r["downgrades_qtd"], brl(r["downgrades_valor"]), "#c0123c")
    )

    th = "padding:8px 10px;background:#0f2438;color:#fff;font-size:11px;text-align:left;white-space:nowrap"
    td = "padding:7px 10px;border-bottom:1px solid #e2e8f0;font-size:12px;white-space:nowrap"
    if downs:
        cab = "".join(f'<th style="{th}">{escape(n)}</th>' for n, _ in COLUNAS_CSV)
        linhas = ""
        for e in downs:
            cels = ""
            for (nome, campo), v in zip(COLUNAS_CSV, _linha(e)):
                if nome == "Intranet":
                    cels += f'<td style="{td}"><a href="{escape(v)}" style="color:#0f9d9a">Abrir</a></td>'
                elif isinstance(v, float):
                    cor = _cor(v) if nome == "Saldo financeiro" else "#0f172a"
                    cels += f'<td style="{td};color:{cor};text-align:right">{brl(v)}</td>'
                else:
                    cels += f'<td style="{td}">{escape("" if v is None else str(v))}</td>'
            linhas += f"<tr>{cels}</tr>"
        tabela = (
            f'<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%">'
            f"<tr>{cab}</tr>{linhas}</table></div>"
            f'<p style="color:#64748b;font-size:12px">A mesma lista segue em anexo (CSV).</p>'
        )
    else:
        tabela = '<p style="color:#475569">Nenhum downgrade registrado neste dia. 🎉</p>'

    return f"""<!doctype html><html><body style="margin:0;background:#f4f6fa;font-family:Segoe UI,Arial,sans-serif;color:#0f172a">
<div style="max-width:1100px;margin:0 auto;padding:20px">
<div style="font-size:11px;letter-spacing:.12em;color:#0f9d9a;font-weight:700">RELATÓRIO DIÁRIO</div>
<h2 style="margin:4px 0 2px">Upgrades e downgrades — {_data_br(dia)}</h2>
<p style="color:#64748b;margin:0 0 12px">Resultado do dia anterior (alterações de plano e/ou duração).</p>
<table style="width:100%;border-collapse:collapse"><tr>{cards}</tr></table>
<h3 style="margin:22px 0 8px">Clientes que fizeram downgrade ({len(downs)})</h3>
{tabela}
</div></body></html>"""


def enviar(destinatarios: list[str], assunto: str, html: str, anexos: list[tuple[str, bytes]]):
    s = config.SMTP
    if not s["host"] or not s["user"]:
        raise RuntimeError("SMTP não configurado no .env")
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = s["sender"]
    msg["To"] = ", ".join(destinatarios)
    msg.set_content("Seu cliente de e-mail não exibe HTML. Veja o CSV em anexo.")
    msg.add_alternative(html, subtype="html")
    for nome, conteudo in anexos:
        msg.add_attachment(conteudo, maintype="text", subtype="csv", filename=nome)

    if s["use_ssl"]:
        server = smtplib.SMTP_SSL(s["host"], s["port"], timeout=30)
    else:
        server = smtplib.SMTP(s["host"], s["port"], timeout=30)
    try:
        if not s["use_ssl"] and s["starttls"]:
            server.starttls()
        server.login(s["user"], s["password"])
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass
