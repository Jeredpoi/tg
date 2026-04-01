#!/bin/bash
# ==============================================================================
# scripts/notify_crash.sh — отправляет Telegram-уведомление при падении бота
# Вызывается из tg-bot-notify.service через systemd OnFailure=
# ==============================================================================

set -e

BOT_DIR="/root/tg"
VENV_PYTHON="${BOT_DIR}/venv/bin/python3"

# Читаем токен и owner_id прямо из config.py — не дублируем секреты
TOKEN=$(${VENV_PYTHON} -c "import sys; sys.path.insert(0,'${BOT_DIR}'); import config; print(config.BOT_TOKEN)")
OWNER=$(${VENV_PYTHON} -c "import sys; sys.path.insert(0,'${BOT_DIR}'); import config; print(config.OWNER_ID)")

TIMESTAMP=$(date '+%d.%m.%Y %H:%M:%S')

# Последние 20 строк journald — чтобы сразу видеть причину падения
JOURNAL=$(journalctl -u tg-bot.service -n 20 --no-pager --output=short 2>/dev/null | tail -20 || echo "журнал недоступен")

MESSAGE="💀 <b>tg-bot упал!</b>

🕐 <b>Время:</b> ${TIMESTAMP}
🖥 <b>Сервер:</b> $(hostname)

<b>Последние строки лога:</b>
<pre>${JOURNAL}</pre>"

curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${OWNER}" \
  --data-urlencode "text=${MESSAGE}" \
  -d "parse_mode=HTML" \
  -d "disable_notification=false" \
  > /dev/null

echo "Crash notification sent at ${TIMESTAMP}"
