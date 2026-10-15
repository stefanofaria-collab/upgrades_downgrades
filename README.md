# Painel de Upgrades e Downgrades

Painel que mede diariamente os upgrades e downgrades (plano e/ou duração) e envia,
todo dia às 09:00 (America/Sao_Paulo), o resultado do dia anterior por e-mail.

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abra http://localhost:8000. O agendador roda **dentro** do processo: o servidor
precisa ficar ligado às 09:00 para o e-mail sair. Rode **um único processo**
(não use `--workers` > 1, senão o e-mail sai duplicado).

## Estrutura

| Arquivo | Função |
|---|---|
| `app/query.sql` | Sua consulta, com período parametrizado |
| `app/analytics.py` | Classificação upgrade/downgrade, cards, série mensal, De→Para |
| `app/mailer.py` | HTML + CSV do e-mail e envio SMTP |
| `app/scheduler.py` | Envio diário às 9h (evita duplicar o mesmo dia) |
| `app/store.py` | SQLite local: destinatários e histórico de envios (`data/app.db`) |
| `static/index.html` | Painel (Visão geral, Movimentações, Downgrades por dia, Envios, Configurações) |

## Regras de cálculo

- Cada pagamento que mudou de plano e/ou duração em relação ao pagamento anterior é uma movimentação, datada por `pago_em`.
- Se só o plano **ou** só a duração mudou, a direção dela define Upgrade/Downgrade.
- Se plano e duração foram em direções opostas, o sinal de `valor atual − valor anterior` decide.
- Saldo = upgrades − downgrades (quantidade). Saldo financeiro = soma das diferenças de valor.

## Segurança

- `.env` está no `.gitignore`. Não o versione.
- Preencha `APP_USER` e `APP_PASSWORD` no `.env` para exigir login no painel (há dados de clientes).
