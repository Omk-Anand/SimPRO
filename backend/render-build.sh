#!/usr/bin/env bash
# Exit on error
set -o errexit

# 1. Install Python packages
pip install --upgrade pip
pip install -r requirements.txt

# 2. Download and extract required system shared libraries into .apt/
echo "Installing Gmsh system dependencies..."
mkdir -p .apt/usr/lib/x86_64-linux-gnu

# Download required deb packages from Ubuntu mirror
DEBS=(
  "http://archive.ubuntu.com/ubuntu/pool/main/libg/libglu/libglu1-mesa_9.0.2-1.1build1_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/x/xft/libxft2_2.3.6-1_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libxcursor/libxcursor1_1.2.0-2build1_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libxinerama/libxinerama1_1.1.4-3_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libxrandr/libxrandr2_1.5.2-1build1_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libxi/libxi6_1.8-1build1_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libx11/libx11-6_1.7.5-1build1_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libxau/libxau6_1.0.9-1build5_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libxdmcp/libxdmcp6_1.1.3-0ubuntu5_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libxext/libxext6_1.3.4-1build1_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libsm/libsm6_1.2.3-1build1_amd64.deb"
  "http://archive.ubuntu.com/ubuntu/pool/main/libx/libice/libice6_1.0.10-1build1_amd64.deb"
)

mkdir -p debs
for deb in "${DEBS[@]}"; do
  curl -sL "$deb" -o debs/pkg.deb
  dpkg-deb -x debs/pkg.deb .apt/
done
rm -rf debs
