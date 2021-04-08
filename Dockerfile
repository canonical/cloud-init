FROM python:3-slim
RUN apt-get update -y
RUN apt-get install -y gcc git
COPY ./requirements.txt /src/
COPY ./test-requirements.txt /src/
COPY ./integration-requirements.txt /src/
WORKDIR /src
RUN pip3 install --upgrade pip
RUN pip3 install --requirement requirements.txt
RUN pip3 install --requirement test-requirements.txt
RUN pip3 install --requirement integration-requirements.txt
RUN pip3 install flake8 pylint
VOLUME /src
ENTRYPOINT ["python", "-m"]

