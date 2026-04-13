FROM python:3.11-slim

WORKDIR /app

# Install build dependencies needed for py-clob-client and crypto packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libssl-dev \
    libffi-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "demo_runner.py"]
