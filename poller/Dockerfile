FROM python:3.11-slim

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /home/appuser/poller

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser

CMD ["python", "main.py"]

