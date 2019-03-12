FROM python:3

COPY . /opt/

RUN pip install --no-cache-dir -r /opt/requirements.txt

ENTRYPOINT ["python3", "/opt/gydytojas.py"]
