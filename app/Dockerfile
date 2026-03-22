FROM python:3.11-slim

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /home/appuser/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser

EXPOSE 5000

CMD ["python", "main.py"]
