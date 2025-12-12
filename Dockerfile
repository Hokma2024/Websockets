FROM python:3.11-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Рабочая директория внутри контейнера
WORKDIR /app

# Сначала копируем только зависимости — это помогает кешировать слой
COPY requirements.txt .

# Установка Python-зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код приложения
COPY . .

#(безопасность)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Сокет-сервер слушает на 8000 (uvicorn)
EXPOSE 8000

# Запуск приложения.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
