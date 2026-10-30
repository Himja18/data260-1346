# HW8 Part 1 - image for the Kafka incident worker and the FastAPI wrapper (s1346).
# Build context is the repository root (see docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY code/kafka_service/requirements.txt /app/code/kafka_service/requirements.txt
RUN pip install --no-cache-dir -r /app/code/kafka_service/requirements.txt

COPY code/hw08_config.py code/kafka_common.py /app/code/
COPY code/kafka_service/ /app/code/kafka_service/

WORKDIR /app/code/kafka_service
# default command = worker; docker-compose overrides it for the API container
CMD ["python", "worker.py"]
