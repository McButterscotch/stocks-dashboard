FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (Docker layer caching:
# if requirements.txt doesn't change, this layer is reused)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
