FROM python:3.12-slim

# gmsh (used for volumetric FEA meshing) needs these system libraries to run
# headlessly — they aren't present in a base Python image or Render's
# default Python buildpack, which is why this Dockerfile exists.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglu1-mesa \
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

