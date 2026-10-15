"""Carrega as movimentações do banco e calcula todos os indicadores do painel."""
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from . import config
from .db import run_query

TZ = ZoneInfo(config.TIMEZONE)
INICIO_HISTORICO = date(2025, 1, 1)
CACHE_TTL = 600  # segundos

EMPRESAS_EXCLUIDAS = [
    1, 24, 43, 2054, 123242, 216321, 346439, 388198, 196044, 10744,
    11807, 166104, 200440, 177551, 209512, 261147, 463295, 458966,
    403472, 226637, 414735, 361435, 376050, 367178, 263918, 447481,
    48142, 438358, 239292, 376338, 479723, 480921, 481136, 479405,
    482279, 124451, 174166, 184848, 186733, 248366, 444241, 462938,
    473336, 476148, 480590, 485458, 487138, 487525, 193364, 267891,
    369137, 484832, 3897, 209986, 334995, 423464, 379294, 278505,
    363585, 202297, 487136, 495757, 74618, 448705, 492276, 493057,
    493495, 495367, 495470, 500211, 500213, 500508, 500582, 502764,
    497959, 510928, 514140, 187078, 521671, 224287, 205324, 517101,
]

NOMES_DURACAO = {"M": "Mensal", "T": "Trimestral", "S": "Semestral", "A": "Anual"}
SEM_ALTERACAO = "Sem alteração"

_SQL = (config.BASE_DIR / "app" / "query.sql").read_text(encoding="utf-8")
_SQL = _SQL.replace("{{EXCLUIDOS}}", ", ".join(str(int(i)) for i in EMPRESAS_EXCLUIDAS))

_cache = {"ts": 0.0, "rows": [], "atualizado_em": None}
_lock = threading.Lock()


def hoje() -> date:
    return datetime.now(TZ).date()


def ontem() -> date:
    return hoje() - timedelta(days=1)


def _f(v) -> float:
    if v is None:
        return 0.0
    return float(v) if isinstance(v, Decimal) else float(v)


def classificar(r: dict) -> str:
    """Upgrade / Downgrade / Neutro de uma movimentação.

    - só plano ou só duração subiu  -> Upgrade (idem Downgrade)
    - plano e duração em direções opostas -> decide pelo sinal da diferença de valor
    """
    flags = {r["alteracao_plano"], r["alteracao_duracao"]} - {SEM_ALTERACAO}
    if flags == {"Upgrade"}:
        return "Upgrade"
    if flags == {"Downgrade"}:
        return "Downgrade"
    dif = r["diferenca_valor"]
    if dif > 0:
        return "Upgrade"
    if dif < 0:
        return "Downgrade"
    return "Neutro"


def _normalizar(r: dict) -> dict:
    e = dict(r)
    for k in ("valor_anterior", "valor_atual", "diferenca_valor"):
        e[k] = _f(e.get(k))
    pago = e["pagamento_atual"]
    e["data"] = pago.date() if isinstance(pago, datetime) else pago
    e["mes"] = e["data"].strftime("%Y-%m")
    e["movimento"] = classificar(e)
    e["duracao_anterior_nome"] = NOMES_DURACAO.get(e.get("duracao_anterior"), e.get("duracao_anterior"))
    e["duracao_atual_nome"] = NOMES_DURACAO.get(e.get("duracao_atual"), e.get("duracao_atual"))
    return e


def eventos(force: bool = False) -> list[dict]:
    with _lock:
        if force or _cache["ts"] == 0 or time.time() - _cache["ts"] > CACHE_TTL:
            fim = hoje() + timedelta(days=1)
            rows = run_query(_SQL, {"inicio": INICIO_HISTORICO.isoformat(), "fim": fim.isoformat()})
            _cache["rows"] = [_normalizar(r) for r in rows]
            _cache["ts"] = time.time()
            _cache["atualizado_em"] = datetime.now(TZ).isoformat(timespec="seconds")
        return _cache["rows"]


def atualizado_em():
    return _cache["atualizado_em"]


# ---------------------------------------------------------------- agregações
def resumo(evs: list[dict]) -> dict:
    ups = [e for e in evs if e["movimento"] == "Upgrade"]
    downs = [e for e in evs if e["movimento"] == "Downgrade"]
    return {
        "upgrades_qtd": len(ups),
        "upgrades_valor": round(sum(e["diferenca_valor"] for e in ups), 2),
        "downgrades_qtd": len(downs),
        "downgrades_valor": round(sum(e["diferenca_valor"] for e in downs), 2),  # negativo
        "saldo_qtd": len(ups) - len(downs),
        "saldo_valor": round(sum(e["diferenca_valor"] for e in ups + downs), 2),
    }


def intervalo(periodo: str, ref: date) -> tuple[date, date]:
    if periodo == "mes_atual":
        return ref.replace(day=1), ref
    if periodo == "mes_anterior":
        fim = ref.replace(day=1) - timedelta(days=1)
        return fim.replace(day=1), fim
    if periodo == "tudo":
        return INICIO_HISTORICO, ref
    try:  # YYYY-MM
        ini = datetime.strptime(periodo, "%Y-%m").date().replace(day=1)
    except ValueError:
        return ref.replace(day=1), ref
    prox = (ini.replace(day=28) + timedelta(days=4)).replace(day=1)
    return ini, min(prox - timedelta(days=1), ref)


def _no_intervalo(evs, ini, fim):
    return [e for e in evs if ini <= e["data"] <= fim]


def _meses(ref: date) -> list[str]:
    out, y, m = [], INICIO_HISTORICO.year, INICIO_HISTORICO.month
    while (y, m) <= (ref.year, ref.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def serie_mensal(evs: list[dict], ref: date) -> list[dict]:
    por_mes = defaultdict(list)
    for e in evs:
        por_mes[e["mes"]].append(e)
    return [{"mes": m, **resumo(por_mes.get(m, []))} for m in _meses(ref)]


def transicoes(evs: list[dict], dimensao: str) -> list[dict]:
    """De -> Para de planos ('plano') ou durações ('duracao')."""
    if dimensao == "plano":
        campo_alt, de_k, para_k = "alteracao_plano", "plano_anterior", "plano_atual"
    else:
        campo_alt, de_k, para_k = "alteracao_duracao", "duracao_anterior_nome", "duracao_atual_nome"
    grupos = defaultdict(lambda: {"qtd": 0, "impacto": 0.0})
    mov = {}
    for e in evs:
        alt = e[campo_alt]
        if alt == SEM_ALTERACAO:
            continue
        chave = (e[de_k], e[para_k])
        grupos[chave]["qtd"] += 1
        grupos[chave]["impacto"] += e["diferenca_valor"]
        mov[chave] = alt
    out = []
    for (de, para), g in grupos.items():
        sinal = 1 if mov[(de, para)] == "Upgrade" else -1
        out.append({
            "de": de, "para": para, "movimento": mov[(de, para)],
            "qtd": g["qtd"], "saldo": sinal * g["qtd"], "impacto": round(g["impacto"], 2),
        })
    return sorted(out, key=lambda x: (-x["qtd"], x["de"] or "", x["para"] or ""))


def downgrades_do_dia(dia: date, evs: list[dict] | None = None) -> list[dict]:
    evs = eventos() if evs is None else evs
    return [e for e in evs if e["data"] == dia and e["movimento"] == "Downgrade"]


def resumo_do_dia(dia: date, evs: list[dict] | None = None) -> dict:
    evs = eventos() if evs is None else evs
    return resumo([e for e in evs if e["data"] == dia])


def visao_geral(periodo: str = "mes_atual", force: bool = False) -> dict:
    evs = eventos(force=force)
    ref = hoje()
    dia = ref - timedelta(days=1)
    ini_m, fim_m = intervalo("mes_atual", ref)
    ini_a, fim_a = intervalo("mes_anterior", ref)
    ini_p, fim_p = intervalo(periodo, ref)
    do_periodo = _no_intervalo(evs, ini_p, fim_p)
    return {
        "atualizado_em": atualizado_em(),
        "hoje": ref.isoformat(),
        "ontem": dia.isoformat(),
        "periodo": {"chave": periodo, "inicio": ini_p.isoformat(), "fim": fim_p.isoformat()},
        "cards": {
            "ontem": resumo_do_dia(dia, evs),
            "mes_atual": resumo(_no_intervalo(evs, ini_m, fim_m)),
            "mes_anterior": resumo(_no_intervalo(evs, ini_a, fim_a)),
            "periodo": resumo(do_periodo),
        },
        "mensal": serie_mensal(evs, ref),
        "planos": transicoes(do_periodo, "plano"),
        "duracoes": transicoes(do_periodo, "duracao"),
        "meses_disponiveis": _meses(ref)[::-1],
    }


def downgrades_json(dia: date) -> list[dict]:
    campos = ["empresa_id", "razao_social", "plano_anterior", "plano_atual", "alteracao_plano",
              "duracao_anterior_nome", "duracao_atual_nome", "alteracao_duracao",
              "valor_anterior", "valor_atual", "diferenca_valor", "nome_usuario",
              "telefone", "celular", "email"]
    out = []
    for e in downgrades_do_dia(dia):
        d = {k: e.get(k) for k in campos}
        d["intranet"] = config.INTRANET_URL.format(empresa_id=e["empresa_id"])
        out.append(d)
    return out
