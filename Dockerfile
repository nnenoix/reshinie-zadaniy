FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/var/app.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY pages ./pages
COPY static ./static
COPY data ./data

RUN useradd --create-home appuser && mkdir -p /app/var && chown appuser /app/var
USER appuser

# База пользователей лежит в /app/var: подключите сюда том, чтобы аккаунты переживали перезапуск.
VOLUME ["/app/var"]
EXPOSE 8000

# Порт берётся из $PORT (так его передают Render и другие хостинги), без него — 8000.
# Заголовки прокси uvicorn не читает: X-Forwarded-For может подделать клиент. Адрес клиента
# за прокси приложение берёт из заголовка CLIENT_IP_HEADER (на Render — cf-connecting-ip).
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port \"${PORT:-8000}\" --no-proxy-headers --no-access-log"]
