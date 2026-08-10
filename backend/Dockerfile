FROM python:3.12-slim

# Install system dependencies required for graphics, OpenGL, and OpenMP (libgomp)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libglu1-mesa \
    libgomp1 \
    libxft2 \
    libxcursor1 \
    libxinerama1 \
    libxrandr2 \
    libxi6 \
    libsm6 \
    libice6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "120", "app:app"]
