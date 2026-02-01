FROM python:3.11-slim

WORKDIR /app

# Install curl for debugging/health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run FastAPI with uvicorn
CMD ["uvicorn", "core.agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
