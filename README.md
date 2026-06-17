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
- `TELEGRAM_CHAT_ID` opcional, para sembrar tu chat inicial
- `WORLD_CUP_TIMEZONE`
- `WORLD_CUP_HOURS`
- `WORLD_CUP_SEND_MODE` con `text`, `image` o `both`

El bot ahora mantiene suscriptores en archivos locales ignorados por Git:

- `data/telegram_subscribers.json`
- `data/telegram_state.json`

Funcionamiento:

- si alguien escribe `/start` al bot, se guarda su `chat_id`, nombre, username y `enabled=true`
- si alguien escribe `/stop`, se mantiene registrado pero pasa a `enabled=false`
- en cada ejecución el bot revisa primero nuevos mensajes y luego envía el resumen a todos los suscriptores activos

Prueba sin enviar:

```bash
python3 scripts/telegram_daily_bot.py --dry-run
```

Enviar mensaje:

```bash
python3 scripts/telegram_daily_bot.py
```

Enviar imagen en vez de texto:

```bash
python3 scripts/telegram_daily_bot.py --send-mode image
```

Enviar ambos:

```bash
python3 scripts/telegram_daily_bot.py --send-mode both
```

Previsualizar imagen:

```bash
python3 scripts/telegram_daily_bot.py --dry-run
python3 scripts/render_matches_image.py --output /tmp/world_cup_matches.png
```

Recursos visuales necesarios para el render:

- `assets/header-cup.png`
- `assets/stadium-bg.jpg`

La carpeta `tmp/` queda solo para pruebas locales y ya no es necesaria para que el bot funcione.

Wrapper pensado para `cron`:

```bash
./scripts/run_daily_bot.sh
```

Ejemplo de `crontab` a las 7:00:

```cron
0 7 * * * cd /home/alfredo/repositorios/world-cup-enjoyer && ./scripts/run_daily_bot.sh >> /tmp/world_cup_bot.log 2>&1
```
