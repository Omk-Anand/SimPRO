FROM python:3.11-slim

# Install system C/OpenGL libraries required by Gmsh and CadQuery
RUN apt-get update && apt-get install -y \
    libglu1-mesa \
    libgl1-mesa-glx \
    libxrender1 \
    libxcursor1 \
    libxft2 \
    libxinerama1 \
    libxext6 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application files
COPY backend/ .

EXPOSE 5000

# Start Gunicorn server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
