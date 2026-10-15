import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")
_extra = os.getenv("CLICKDADOS_ENV_PATH", "").strip()
if _extra and Path(_extra).exists():
    load_dotenv(_extra, override=False)


def _bool(v: str | None, default=False) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "sim", "on")


DB = dict(
    host=os.getenv("DB_HOST", ""),
    port=int(os.getenv("DB_PORT", "3306")),
    database=os.getenv("DB_NAME", ""),
    user=os.getenv("DB_USER", ""),
    password=os.getenv("DB_PASSWORD", ""),
    charset=os.getenv("DB_CHARSET", "utf8mb4"),
)

SMTP = dict(
    host=os.getenv("SMTP_HOST", ""),
    port=int(os.getenv("SMTP_PORT", "587")),
    user=os.getenv("SMTP_USER", ""),
    password=os.getenv("SMTP_PASS", ""),
    sender=os.getenv("SMTP_FROM", "") or os.getenv("SMTP_USER", ""),
    use_ssl=_bool(os.getenv("SMTP_USE_SSL")),
    starttls=_bool(os.getenv("SMTP_STARTTLS"), True),
)

TIMEZONE = os.getenv("APP_TIMEZONE", "America/Sao_Paulo")
SEND_HOUR = int(os.getenv("SEND_HOUR", "9"))
SEND_MINUTE = int(os.getenv("SEND_MINUTE", "0"))
APP_USER = os.getenv("APP_USER", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

INTRANET_URL = "https://intranet.clickdigital.com.br/clientes/visualizar/{empresa_id}?aba=5"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
