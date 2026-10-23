FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install OS-level dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Expose the service port (dev: 5200)
EXPOSE 5200

# Run migrations then start the Django development server
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:5200"]
