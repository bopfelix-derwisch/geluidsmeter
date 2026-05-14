#!/usr/bin/env bash
# Eenmalige setup van Cloudflare Tunnel voor geluid.felixisfelix.com
# Voer dit script NIET automatisch uit — het vereist interactieve browser-login.
set -e

echo "=== Stap 1: cloudflared installeren (arm64) ==="
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o /tmp/cloudflared
sudo install /tmp/cloudflared /usr/local/bin/cloudflared
cloudflared --version

echo "=== Stap 2: Authenticeren met Cloudflare ==="
echo "Dit opent een URL — ga ernaar in je browser en autoriseer felixisfelix.com"
cloudflared tunnel login

echo "=== Stap 3: Tunnel aanmaken ==="
cloudflared tunnel create geluidsmeter

echo "=== Stap 4: Config aanmaken ==="
TUNNEL_ID=$(cloudflared tunnel list --output json | python3 -c "import sys,json; tunnels=json.load(sys.stdin); print(next(t['id'] for t in tunnels if t['name']=='geluidsmeter'))")
echo "Tunnel ID: $TUNNEL_ID"

cat > ~/.cloudflared/config.yml << EOF
tunnel: ${TUNNEL_ID}
credentials-file: /home/bob/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: geluid.felixisfelix.com
    service: http://localhost:8792
  - service: http_status:404
EOF

echo "=== Stap 5: DNS koppelen ==="
cloudflared tunnel route dns geluidsmeter geluid.felixisfelix.com

echo "=== Stap 6: Systemd service installeren ==="
sudo cp /home/bob/Geluidsmeter/systemd/geluidsmeter-tunnel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now geluidsmeter-tunnel.service
sudo systemctl status geluidsmeter-tunnel.service

echo "=== Klaar! Test: curl https://geluid.felixisfelix.com/health ==="
