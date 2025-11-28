# 使用 Python + Poetry 官方映像
FROM python:3.12-slim

# 安裝系統套件與 Poetry
RUN apt-get update && apt-get install -y curl build-essential && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# 設定工作目錄
WORKDIR /app

# 複製專案檔案
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
 && poetry install --no-interaction --no-ansi --no-root

# 複製應用程式與靜態資源
COPY ./src ./src
COPY ./static ./static

# FastAPI 專案入口點
ENV PYTHONPATH=/app/src

# 對外開放 port
EXPOSE 8088

# 啟動 FastAPI
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8088"]

