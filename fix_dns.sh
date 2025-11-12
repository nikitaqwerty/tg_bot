#!/bin/bash
# DNS Fix Script for Remote Server

echo "🔍 Diagnosing DNS issues..."

# Test DNS resolution
echo "Testing DNS resolution..."
nslookup registry-1.docker.io 8.8.8.8 || echo "❌ DNS resolution failed"

# Check systemd-resolved status
echo ""
echo "Checking systemd-resolved status..."
systemctl status systemd-resolved --no-pager

# Add Google DNS as fallback
echo ""
echo "🔧 Configuring DNS with Google DNS (8.8.8.8)..."

# Backup original resolv.conf
cp /etc/resolv.conf /etc/resolv.conf.backup

# Configure Docker daemon to use Google DNS
echo "Configuring Docker daemon DNS..."
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'DOCKER_EOF'
{
  "dns": ["8.8.8.8", "8.8.4.4"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
DOCKER_EOF

# Restart Docker service
echo "Restarting Docker service..."
systemctl restart docker
sleep 5

echo ""
echo "✅ DNS configuration updated!"
echo "Testing Docker Hub connectivity..."
docker pull hello-world && echo "✅ Docker Hub is now accessible!" || echo "❌ Still having issues"
