FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt update
RUN apt upgrade -y
RUN apt install python3-pip -y
RUN pip install flask
RUN pip install requests
RUN pip install httpx
RUN pip install flask-cors

COPY . .

RUN chmod +x ./start.sh
CMD ["/usr/bin/bash", "./start.sh"]