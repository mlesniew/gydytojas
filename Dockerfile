FROM python:2

COPY . /opt/

RUN pip install --no-cache-dir -r /opt/requirements.txt

ENV PYTHONIOENCODING utf-8
CMD [ "python", "/opt/gydytojas.py" ]
