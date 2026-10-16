FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 GOOGLE_GENAI_USE_VERTEXAI=FALSE
COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt
COPY pota_bot ./pota_bot
COPY server ./server
CMD exec uvicorn server.production:app --host 0.0.0.0 --port ${PORT:-8080}
