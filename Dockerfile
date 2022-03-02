FROM python:3-slim

LABEL org.opencontainers.image.source=https://github.com/mlesniew/gydytojas

COPY gydytojas.py requirements.txt /app/

RUN pip install --no-cache-dir -r /app/requirements.txt

ENTRYPOINT ["python3", "/app/gydytojas.py"]
