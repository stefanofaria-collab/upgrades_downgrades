import secrets
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from . import analytics, config, scheduler, store

security = HTTPBasic(auto_error=False)


def autenticar(cred: HTTPBasicCredentials | None = Depends(security)):
    """Se APP_USER/APP_PASSWORD estiverem no .env, exige login (os dados são de clientes)."""
    if not config.APP_PASSWORD:
        return
    ok = (
        cred is not None
        and secrets.compare_digest(cred.username, config.APP_USER)
        and secrets.compare_digest(cred.password, config.APP_PASSWORD)
    )
    if not ok:
        raise HTTPException(401, "Não autorizado", headers={"WWW-Authenticate": "Basic"})


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init()
    scheduler.iniciar()
    yield
    scheduler.parar()


app = FastAPI(title="Upgrades e Downgrades", lifespan=lifespan, dependencies=[Depends(autenticar)])


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(config.BASE_DIR / "static" / "index.html")


@app.get("/api/overview")
def overview(periodo: str = "mes_atual", atualizar: bool = False):
    try:
        return analytics.visao_geral(periodo, force=atualizar)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Falha ao consultar o banco: {exc}")


@app.get("/api/downgrades")
def downgrades(data: date | None = Query(None)):
    try:
        dia = data or analytics.ontem()
        return {"data": dia.isoformat(), "itens": analytics.downgrades_json(dia)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Falha ao consultar o banco: {exc}")


class EmailIn(BaseModel):
    email: str


@app.get("/api/config")
def get_config():
    return {
        "destinatarios": store.listar_destinatarios(),
        "horario_envio": f"{config.SEND_HOUR:02d}:{config.SEND_MINUTE:02d}",
        "fuso": config.TIMEZONE,
        "smtp_configurado": bool(config.SMTP["host"] and config.SMTP["user"]),
    }


@app.post("/api/destinatarios")
def add_dest(body: EmailIn):
    try:
        store.adicionar_destinatario(body.email)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"destinatarios": store.listar_destinatarios()}


@app.delete("/api/destinatarios")
def del_dest(email: str):
    store.remover_destinatario(email)
    return {"destinatarios": store.listar_destinatarios()}


@app.get("/api/envios")
def envios():
    return store.listar_envios()


@app.post("/api/enviar-agora")
def enviar_agora(data: date | None = None):
    """Dispara o e-mail manualmente (padrão: resultado de ontem)."""
    return scheduler.enviar_relatorio(data, forcar=True)
