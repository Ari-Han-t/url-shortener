#!/usr/bin/env bash
# Download the free DB-IP "IP to City Lite" database (CC BY 4.0, https://db-ip.com)
# into data/dbip-city-lite.mmdb. Tries this month's file, then last month's.
# The new file is moved into place atomically, so a running app never sees a partial file.
set -euo pipefail

DEST_DIR="${GEOIP_DIR:-$(cd "$(dirname "$0")/.." && pwd)/data}"
DEST="$DEST_DIR/dbip-city-lite.mmdb"
mkdir -p "$DEST_DIR"

month_back() {  # $1 = months back; prints YYYY-MM (UTC)
  date -u -d "$(date -u +%Y-%m-01) -$1 month" +%Y-%m 2>/dev/null \
    || date -u -v-"$1"m +%Y-%m  # BSD/macOS fallback
}

TMP="$(mktemp "$DEST_DIR/.dbip.XXXXXX")"
trap 'rm -f "$TMP" "$TMP.gz"' EXIT

for back in 0 1; do
  ym="$(month_back "$back")"
  url="https://download.db-ip.com/free/dbip-city-lite-$ym.mmdb.gz"
  echo "Trying $url"
  code="$(curl -sS -L -o "$TMP.gz" -w '%{http_code}' "$url" || true)"
  if [ "$code" = "200" ]; then
    gunzip -c "$TMP.gz" > "$TMP"
    chmod 644 "$TMP"
    mv -f "$TMP" "$DEST"
    echo "Installed $DEST ($ym). IP geolocation by DB-IP (https://db-ip.com)."
    exit 0
  fi
  echo "  HTTP $code, trying the previous month"
done

echo "Could not download the DB-IP City Lite database." >&2
exit 1
