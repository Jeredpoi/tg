# 🤖 ChatBot — Telegram-бот для чата

Telegram-бот на Python с командами `/roast`, `/dice`, `/king`, `/top`, `/rate`, статистикой участников и системой оценки фото.

---

## 📁 Структура проекта

```
bot/
├── bot.py           # Точка входа, регистрация хендлеров
├── config.py        # Токен и ID чата
├── database.py      # Работа с SQLite
├── requirements.txt
├── README.md
└── commands/
    ├── __init__.py
    ├── roast.py     # /roast — обсмеять пользователя
    ├── dice.py      # /dice — кубик
    ├── king.py      # /king — король чата
    ├── top.py       # /top — статистика
    └── rate.py      # /rate — оценка фото
```

---

## ⚙️ Установка

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO/bot
```

### 2. Создайте виртуальное окружение

```bash
python3.11 -m venv venv
source venv/bin/activate        # Linux / macOS
# или
venv\Scripts\activate           # Windows
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

---

## 🔑 Получение токена бота

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather)
2. Отправьте команду `/newbot`
3. Следуйте инструкциям — введите имя и username бота
4. Скопируйте полученный **токен**

---

## 🆔 Как узнать CHAT_ID

**Способ 1 — через @userinfobot:**
1. Добавьте [@userinfobot](https://t.me/userinfobot) в ваш чат
2. Бот сообщит ID чата

**Способ 2 — через getUpdates:**
1. Добавьте бота в чат
2. Отправьте любое сообщение
3. Откройте в браузере:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
4. Найдите поле `"chat"` → `"id"` в JSON-ответе

---

## 🛠 Настройка

Откройте `config.py` и заполните:

```python
BOT_TOKEN = "1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
CHAT_ID   = -1001234567890   # ID вашего чата (обычно отрицательный для групп)
```

---

## 🚀 Запуск

```bash
python bot.py
```

---

## 📋 Команды бота

| Команда | Описание |
|---------|----------|
| `/roast @username` | Случайная шутка над пользователем |
| `/dice` | Бросить кубик 🎲 |
| `/king` | Случайный король чата 👑 |
| `/top` | Статистика чата (сообщения / маты) |
| `/rate` | Оценить фото (ответьте на фото командой) |

---

## 🌐 Деплой на сервер

### Вариант 1: Systemd (Linux VPS)

1. Загрузите файлы на сервер:
   ```bash
   scp -r bot/ user@YOUR_SERVER:/home/user/chatbot
   ```

2. Создайте юнит-файл:
   ```bash
   sudo nano /etc/systemd/system/chatbot.service
   ```

   ```ini
   [Unit]
   Description=Telegram ChatBot
   After=network.target

   [Service]
   User=user
   WorkingDirectory=/home/user/chatbot
   ExecStart=/home/user/chatbot/venv/bin/python bot.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. Запустите и добавьте в автозагрузку:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable chatbot
   sudo systemctl start chatbot
   sudo systemctl status chatbot
   ```

### Вариант 2: Docker

Создайте `Dockerfile` рядом с папкой `bot/`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY bot/ .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "bot.py"]
```

```bash
docker build -t chatbot .
docker run -d --name chatbot --restart unless-stopped chatbot
```

### Вариант 3: Railway / Render / Fly.io

1. Опубликуйте репозиторий на GitHub
2. Создайте новый проект на выбранной платформе
3. Укажите переменные окружения `BOT_TOKEN` и `CHAT_ID`
   (при необходимости адаптируйте `config.py` для чтения из `os.environ`)
4. Платформа сама установит зависимости и запустит `python bot.py`

---

## 🗄 База данных

Бот создаёт `bot_stats.db` (SQLite) автоматически при первом запуске.

Таблицы:
- `user_stats` — счётчики сообщений и матов по каждому пользователю
- `photo_ratings` — данные оцениваемых фото
- `photo_votes` — голоса пользователей за фото

---

## 📝 Лицензия

MIT — используйте как хотите.
