FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt update
RUN apt upgrade -y
RUN apt install python3-pip -y
RUN apt install gcc
RUN apt install make
RUN apt install bash
RUN apt install curl
RUN apt install wget
RUN apt install git
RUN git clone https://github.com/dougy147/mcbash
RUN cd ./mcbash
RUN make install
RUN cd ../

RUN pip install flask
RUN pip install requests

COPY . .

CMD ["python", "main.py"]