FROM python:3.11-slim

WORKDIR /app

COPY requirements-railway.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-railway.txt

# Create /data directory for persistent DB (mount Railway volume here)
RUN mkdir -p /data

# Set DB_PATH so trades.db persists across redeploys when Railway volume is mounted at /data
ENV DB_PATH=/data/trades.db

COPY . .

EXPOSE 8081
CMD ["python", "run_both.py"]
