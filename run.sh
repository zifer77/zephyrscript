#!/usr/bin/env bash
# Jalankan backend ZephyrScript (dev). Pakai: ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

# 1) .env + JWT_SECRET otomatis
[ -f .env ] || cp .env.example .env
if ! grep -qE '^JWT_SECRET=.+' .env; then
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  if grep -q '^JWT_SECRET=' .env; then
    sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${SECRET}|" .env
  else
    echo "JWT_SECRET=${SECRET}" >> .env
  fi
  echo "[run.sh] JWT_SECRET dibuat otomatis di .env"
fi

# 2) Dependensi (jika belum terpasang)
python3 -c "import fastapi" 2>/dev/null || pip install -r requirements.txt

# 3) Codespaces: coba set port jadi public (gagal = set manual lewat tab PORTS)
if [ -n "${CODESPACE_NAME:-}" ]; then
  if command -v gh >/dev/null 2>&1; then
    gh codespace ports visibility "${PORT}:public" 5173:public -c "$CODESPACE_NAME" >/dev/null 2>&1 \
      || echo "[run.sh] Gagal set port public otomatis -> tab PORTS > klik kanan port > Port Visibility > Public"
  fi
  DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  URL="https://${CODESPACE_NAME}-${PORT}.${DOMAIN}"
else
  URL="http://localhost:${PORT}"
fi

# uvicorn berjalan di foreground, jadi URL dicetak sebelum server start
echo
echo "=============================================="
echo "  ZephyrScript API : ${URL}"
echo "  Health check     : ${URL}/api/health"
echo "  Swagger docs     : ${URL}/docs"
echo "=============================================="
echo

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --reload
