FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt update
RUN apt upgrade -y
RUN apt install python3-pip -y
RUN apt install gcc -y
RUN apt install make -y
RUN apt install bash -y
RUN apt install curl -y
RUN apt install wget -y
RUN apt install git -y
RUN apt install bc -y
RUN git clone https://github.com/dougy147/mcbash
RUN mv ./mcbash/* ./
RUN make install

RUN pip install flask
RUN pip install requests
RUN pip install httpx
RUN apt install ffmpeg -y
RUN pip install flask-cors

COPY . .

CMD ["python", "main.py"]