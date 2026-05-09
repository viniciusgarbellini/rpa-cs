FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.5 uvicorn[standard]==0.32.1

COPY app.py ./

ENV SENSOR_API_PORT=8002
EXPOSE 8002

CMD ["python", "app.py"]
