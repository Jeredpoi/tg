#!/bin/bash
# Автоматическая настройка nginx + SSL + запуск вебсервера

set -e

echo "==> Устанавливаем nginx и certbot..."
apt update -q && apt install -y nginx certbot python3-certbot-nginx

echo "==> Устанавливаем aiohttp..."
pip install -q aiohttp

echo "==> Создаём конфиг nginx..."
cat > /etc/nginx/sites-available/bottgmge.com << 'NGINXCONF'
server {
    listen 80;
    server_name bottgmge.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }

    location / {
        root /root/tg/webapp;
        try_files $uri /index.html;
    }
}
NGINXCONF

echo "==> Подключаем конфиг..."
ln -sf /etc/nginx/sites-available/bottgmge.com /etc/nginx/sites-enabled/bottgmge.com
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> Получаем SSL сертификат..."
certbot --nginx -d bottgmge.com --non-interactive --agree-tos -m admin@bottgmge.com

echo "==> Создаём systemd сервис для вебсервера..."
cat > /etc/systemd/system/tg-webserver.service << 'SERVICECONF'
[Unit]
Description=TG Bot Webserver
After=network.target

[Service]
WorkingDirectory=/root/tg
ExecStart=/usr/bin/python3 /root/tg/webserver.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICECONF

systemctl daemon-reload
systemctl enable tg-webserver
systemctl start tg-webserver

echo ""
echo "✅ Готово! Сайт доступен на https://bottgmge.com"
echo "   Вебсервер запущен как systemd сервис (tg-webserver)"
echo "   Проверить статус: systemctl status tg-webserver"
