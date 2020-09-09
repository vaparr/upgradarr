FROM python:3.8.0-slim as RadarrDownloader
ARG HOST
ARG APIKEY
COPY src/RadarrDownloader.py /app/RadarrDownloader.py
WORKDIR app
ENV PATH=/root/.local/bin:$PATH
RUN pip3 install requests
ENTRYPOINT ["python3", "/app/RadarrDownloader.py"]
VOLUME /config
