FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY run.py .

ENV DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 5000

CMD ["python", "run.py"]
