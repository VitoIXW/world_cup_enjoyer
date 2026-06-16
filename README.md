# world-cup-enjoyer

Base para un bot diario de Telegram sobre la Copa Mundial de la FIFA 2026.

## Fuente oficial encontrada

La web oficial de FIFA en:

`https://www.fifa.com/es/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures?country=ES&wtw-filter=ALL`

usa estas llamadas internas:

- `https://cxm-api.fifa.com/fifaplusweb/api/pages/es/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures`
- `https://cxm-api.fifa.com/fifaplusweb/api/sections/whereToWatch/...`
- `https://api.fifa.com/api/v3/calendar/matches?language=es&count=500&idSeason=...`

Con eso evitamos scraping del HTML y tiramos de datos oficiales.

## Script actual

Para sacar partidos de las próximas 24 horas en horario de Madrid:

```bash
python3 scripts/fifa_upcoming_matches.py
```

Salida JSON:

```bash
python3 scripts/fifa_upcoming_matches.py --format json
```

Cambiar ventana:

```bash
python3 scripts/fifa_upcoming_matches.py --hours 12
```

Cambiar zona horaria:

```bash
python3 scripts/fifa_upcoming_matches.py --timezone Europe/Madrid
```

## Bot de Telegram

Copia `.env.example` a `.env` y rellena:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `WORLD_CUP_TIMEZONE`
- `WORLD_CUP_HOURS`

Prueba sin enviar:

```bash
python3 scripts/telegram_daily_bot.py --dry-run
```

Enviar mensaje:

```bash
python3 scripts/telegram_daily_bot.py
```

Wrapper pensado para `cron`:

```bash
./scripts/run_daily_bot.sh
```

Ejemplo de `crontab` a las 7:00:

```cron
0 7 * * * cd /home/alfredo/repositorios/world-cup-enjoyer && ./scripts/run_daily_bot.sh >> /tmp/world_cup_bot.log 2>&1
```
