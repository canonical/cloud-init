FROM python:3-alpine
COPY ./requirements.txt /src/
COPY ./test-requirements.txt /src/
WORKDIR /src
RUN apk add bash
RUN pip3 install --upgrade pip
RUN pip3 install --requirement requirements.txt
RUN pip3 install --requirement test-requirements.txt
RUN pip3 install flake8 pylint
VOLUME /src

