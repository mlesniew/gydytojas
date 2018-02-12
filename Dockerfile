FROM python:2

COPY . /opt/

RUN pip install --no-cache-dir -r /opt/requirements.txt

CMD [ "python", "/opt/gydytojas.py" ]
