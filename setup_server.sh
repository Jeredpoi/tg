#!/bin/bash
# Автоматическая настройка nginx + SSL + запуск вебсервера

set -e

DOMAIN="144.31.75.246.sslip.io"

echo "==> Устанавливаем nginx и certbot..."
apt update -q && apt install -y nginx certbot python3-certbot-nginx

echo "==> Создаём виртуальное окружение..."
python3 -m venv /root/tg/venv

echo "==> Устанавливаем зависимости Python..."
/root/tg/venv/bin/pip install -q --upgrade pip
/root/tg/venv/bin/pip install -q -r /root/tg/requirements.txt
/root/tg/venv/bin/pip install -q aiohttp httpx

echo "==> Создаём конфиг nginx..."
cat > /etc/nginx/sites-available/${DOMAIN} << NGINXCONF
server {
    listen 80;
    server_name ${DOMAIN};

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
    }

    location / {
        root /root/tg/webapp;
        try_files \$uri /index.html;
    }
}
NGINXCONF

echo "==> Подключаем конфиг..."
ln -sf /etc/nginx/sites-available/${DOMAIN} /etc/nginx/sites-enabled/${DOMAIN}
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> Получаем SSL сертификат..."
certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m admin@${DOMAIN}

echo "==> Создаём сервис для бота..."
cat > /etc/systemd/system/tg-bot.service << 'BOTCONF'
[Unit]
Description=TG Bot
After=network.target

[Service]
WorkingDirectory=/root/tg
ExecStart=/root/tg/venv/bin/python3 /root/tg/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
BOTCONF

echo "==> Создаём сервис для вебсервера..."
cat > /etc/systemd/system/tg-webserver.service << 'WEBCONF'
[Unit]
Description=TG Webserver
After=network.target

[Service]
WorkingDirectory=/root/tg
ExecStart=/root/tg/venv/bin/python3 /root/tg/webserver.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
WEBCONF

echo "==> Останавливаем старый сервис и запускаем оба..."
systemctl daemon-reload
systemctl stop tg-webserver 2>/dev/null || true
systemctl disable tg-webserver 2>/dev/null || true
systemctl enable tg-bot tg-webserver
systemctl start tg-bot tg-webserver

echo ""
echo "✅ Готово!"
echo "   Сайт: https://${DOMAIN}"
echo "   Статус бота:      systemctl status tg-bot"
echo "   Статус вебсервера: systemctl status tg-webserver"
