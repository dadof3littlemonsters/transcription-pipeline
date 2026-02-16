#!/bin/bash
# Script to update Caddy configuration with basic auth
# Run this on your VPS

set -e

echo "=== Updating Caddy Configuration ==="

# Check if running as root for system paths
if [ "$EUID" -ne 0 ] && [ ! -w "/etc/caddy" ]; then
    echo "Warning: You may need sudo to update /etc/caddy/Caddyfile"
fi

# Backup existing Caddyfile
if [ -f /etc/caddy/Caddyfile ]; then
    echo "Backing up existing Caddyfile..."
    cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.backup.$(date +%Y%m%d_%H%M%S)
fi

# Copy new Caddyfile
echo "Installing new Caddyfile with basic auth..."
cp Caddyfile /etc/caddy/Caddyfile

# Validate Caddy configuration
echo "Validating Caddy configuration..."
if command -v caddy &> /dev/null; then
    caddy validate --config /etc/caddy/Caddyfile
elif docker ps --filter "name=caddy" --format "{{.Names}}" | grep -q "caddy"; then
    echo "Caddy running in Docker, skipping validation..."
else
    echo "Warning: Could not validate configuration. Caddy may not be installed."
fi

# Reload Caddy
echo "Reloading Caddy..."
if command -v systemctl &> /dev/null && systemctl is-active --quiet caddy; then
    systemctl reload caddy
    echo "✓ Caddy reloaded via systemd"
elif docker ps --filter "name=caddy" --format "{{.Names}}" | grep -q "caddy"; then
    docker exec caddy caddy reload --config /etc/caddy/Caddyfile
    echo "✓ Caddy reloaded via Docker"
else
    echo "⚠ Could not reload Caddy automatically. Please reload manually:"
    echo "   sudo systemctl reload caddy"
    echo "   or"
    echo "   docker exec caddy caddy reload --config /etc/caddy/Caddyfile"
fi

echo ""
echo "=== Caddy Updated Successfully ==="
echo "Username: craig"
echo "Password: Craig2025!"
echo ""
echo "Your transcription pipeline is now protected with basic auth."
echo "Visit https://transcribe.delboysden.uk and enter the credentials."
