#!/bin/bash
set -euo pipefail

# ---------------------------
# LOAD CREDENTIALS
# ---------------------------
# Stored in a secure file outside the Git repo
ENV_FILE="/home/grstathis/.cinema_env"
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
else
    echo "ERROR: Credential file $ENV_FILE not found!"
    exit 1
fi

# ---------------------------
# CONFIGURATION
# ---------------------------
PYTHON="/home/grstathis/bin/python3"
SCRIPT="/home/grstathis/ti-paizei-tora.gr/athinorama_cinema_info.py"
LOCAL_DIR="/home/grstathis/ti-paizei-tora.gr"
REMOTE_DIR="/httpdocs"
FTP_HOST="ftp.ti-paizei-tora.gr"
FTP_PORT="21"

FILES=(
    "cinemas.json"
    "movies.json"
    "cinema_database.json"
    "sitemap.xml"
)

LOGFILE="/home/grstathis/cinema_update.log"
mkdir -p "$(dirname "$LOGFILE")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S')  $1" | tee -a "$LOGFILE"
}

# ---------------------------
# RUN PYTHON SCRIPT
# ---------------------------
log "Running Python generator script..."
"$PYTHON" "$SCRIPT"
log "Python script finished."

# ---------------------------
# FTP UPLOAD
# ---------------------------
log "Uploading generated files via FTP..."

lftp -u "$FTP_USER","$FTP_PASS" -p "$FTP_PORT" "ftp://$FTP_HOST" <<EOF
set ftp:ssl-auth TLS;
set ftp:ssl-force true;
set ssl:check-hostname no;
set ftp:sync-mode off;


$(for f in "${FILES[@]}"; do
echo "put -O $REMOTE_DIR $LOCAL_DIR/$f;"
done)

# Upload folders recursively
mirror -R -P 5  --no-symlinks $LOCAL_DIR/movie $REMOTE_DIR/movie;
mirror -R -P 5  --no-symlinks $LOCAL_DIR/region $REMOTE_DIR/region;

bye
EOF

log "Upload completed successfully."

