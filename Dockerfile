FROM python:3.12-slim

# Installera systemberoenden (ex. build-essential behövs ofta för att bygga Python‑paket)
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Sätt arbetskatalogen
WORKDIR /app

# Kopiera pip-kravfilen och installera beroenden
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiera övriga källkoden
COPY . .

# Starta applikationen
CMD ["python", "main.py"]
