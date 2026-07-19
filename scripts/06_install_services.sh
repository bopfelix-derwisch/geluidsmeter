#!/usr/bin/env bash
# Installeer geluidsmeter-api als systemd service en koppel geluid.felixisfelix.com
# aan de bestaande Cloudflare tunnel.
# Gebruik: sudo bash 06_install_services.sh
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "❌  Voer uit met sudo: sudo bash 06_install_services.sh"
  exit 1
fi

BOB_HOME="/home/bob"
SERVICE_SRC="$BOB_HOME/Geluidsmeter/systemd/leefomgevinglab-api.service"
SERVICE_DST="/etc/systemd/system/leefomgevinglab-api.service"

echo "=== Stap 1: API service installeren ==="
cp "$SERVICE_SRC" "$SERVICE_DST"
systemctl daemon-reload
systemctl enable --now leefomgevinglab-api.service
echo "✓ leefomgevinglab-api.service actief"

echo ""
echo "=== Stap 2: cloudflared herstarten (pikt geluid.felixisfelix.com op) ==="
systemctl restart cloudflared
sleep 2
systemctl is-active cloudflared && echo "✓ cloudflared actief" || echo "❌ cloudflared probleem"

echo ""
echo "=== Stap 3: DNS-route aanmaken voor geluid.felixisfelix.com ==="
# Draai als bob — cloudflared credentials staan in /home/bob/.cloudflared/
TUNNEL_ID=$(sudo -u bob cloudflared tunnel list --output json 2>/dev/null \
  | python3 -c "import sys,json; tunnels=json.load(sys.stdin); print(tunnels[0]['id'])" 2>/dev/null || true)

if [ -n "$TUNNEL_ID" ]; then
  sudo -u bob cloudflared tunnel route dns "$TUNNEL_ID" geluid.felixisfelix.com \
    && echo "✓ DNS-route geluid.felixisfelix.com → tunnel $TUNNEL_ID" \
    || echo "⚠  DNS-route mislukt (mogelijk al aanwezig — dat is ok)"
else
  echo "⚠  Tunnel ID niet gevonden — DNS-route overgeslagen."
  echo "   Voer handmatig uit: cloudflared tunnel route dns <TUNNEL_ID> geluid.felixisfelix.com"
fi

echo ""
echo "=== Verificatie ==="
sleep 2
curl -s http://localhost:8792/health && echo ""
systemctl status leefomgevinglab-api.service --no-pager -l | grep -E "Active|Main PID"

echo ""
echo "=== Klaar ==="
echo "Lokaal:   http://localhost:8792/health"
echo "Publiek:  https://geluid.felixisfelix.com/health  (DNS kan 1-2 min duren)"
