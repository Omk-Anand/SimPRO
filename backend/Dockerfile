FROM python:3.12-slim

# gmsh, cadquery, and vtk (used for volumetric FEA/CAD generation) 
# need these system libraries to run headlessly in a slim container.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libgl1-mesa-glx \
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
