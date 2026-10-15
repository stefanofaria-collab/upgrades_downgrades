"""Envio diário do resultado do dia anterior (padrão: 09:00, fuso de São Paulo)."""
import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler

from . import analytics, config, mailer, store

log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None


def enviar_relatorio(data_ref: date | None = None, forcar: bool = False) -> dict:
    data_ref = data_ref or analytics.ontem()
    dests = store.listar_destinatarios()
    if not dests:
        store.registrar_envio(data_ref, "ignorado", "", erro="Nenhum destinatário cadastrado")
        return {"status": "ignorado", "mensagem": "Nenhum destinatário cadastrado."}
    if not forcar and store.ja_enviado(data_ref):
        return {"status": "ignorado", "mensagem": "Relatório desse dia já foi enviado."}
    try:
        evs = analytics.eventos(force=True)
        r = analytics.resumo_do_dia(data_ref, evs)
        downs = analytics.downgrades_do_dia(data_ref, evs)
        sinal = f"+{r['saldo_qtd']}" if r["saldo_qtd"] > 0 else str(r["saldo_qtd"])
        assunto = f"Upgrades e downgrades {data_ref:%d/%m/%Y} | saldo {sinal}"
        html = mailer.gerar_html(data_ref, r, downs)
        csv_bytes = mailer.gerar_csv(downs)
        mailer.enviar(dests, assunto, html, [(f"downgrades_{data_ref:%Y-%m-%d}.csv", csv_bytes)])
        store.registrar_envio(data_ref, "enviado", dests, r["upgrades_qtd"], r["downgrades_qtd"], r["saldo_qtd"])
        return {"status": "enviado", "mensagem": f"Enviado para {len(dests)} destinatário(s)."}
    except Exception as exc:  # noqa: BLE001
        log.exception("Falha ao enviar relatório")
        store.registrar_envio(data_ref, "erro", dests, erro=str(exc)[:500])
        return {"status": "erro", "mensagem": str(exc)}


def iniciar():
    global _scheduler
    _scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
    _scheduler.add_job(
        enviar_relatorio, "cron",
        hour=config.SEND_HOUR, minute=config.SEND_MINUTE,
        id="relatorio_diario", coalesce=True, misfire_grace_time=3600,
        replace_existing=True,
    )
    _scheduler.start()


def parar():
    if _scheduler:
        _scheduler.shutdown(wait=False)
