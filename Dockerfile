FROM python:3.11-slim

WORKDIR /app

COPY requirements-railway.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-railway.txt

COPY . .

EXPOSE 8080
CMD ["python", "run_both.py"]
