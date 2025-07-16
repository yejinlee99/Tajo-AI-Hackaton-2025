# Dockerfile
FROM python:3.11-slim

# Set workdir
WORKDIR /app

# Copy requirements first to leverage cache
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the app
COPY . .

# Expose port
EXPOSE 5050

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5050"]
