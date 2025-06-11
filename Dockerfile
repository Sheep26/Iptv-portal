FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt update
RUN apt upgrade -y
RUN apt install python3-pip -y
RUN pip install flask
RUN pip install requests

COPY . .

CMD ["python", "main.py"]