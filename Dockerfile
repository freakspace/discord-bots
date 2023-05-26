ARG PYTHON_VERSION=3.9-slim-buster

FROM python:${PYTHON_VERSION} as python

WORKDIR /lifty

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "./run.py"]