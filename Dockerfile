FROM python:3-slim

RUN pip3 install prometheus_client requests

ADD exporter.py /usr/local/bin/teslafi_exporter

EXPOSE 9998/tcp

ENTRYPOINT [ "/usr/local/bin/teslafi_exporter" ]
