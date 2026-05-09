FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.5 uvicorn[standard]==0.32.1

COPY app.py ./

ENV LEGACY_API_PORT=8001
EXPOSE 8001

CMD ["python", "app.py"]
