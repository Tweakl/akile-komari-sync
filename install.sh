#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/akile-komari-sync"
SCRIPT_NAME="sync_akile_komari.py"
SERVICE_NAME="akile-komari-sync"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}.timer"
DEFAULT_INTERVAL="1h"
DEFAULT_SYNC_SCRIPT_URL="https://raw.githubusercontent.com/Tweakl/akile-komari-sync/main/sync_akile_komari.py"

need_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 权限运行。"
    exit 1
  fi
}

read_required() {
  local prompt="$1"
  local value=""
  while [ -z "$value" ]; do
    read -r -p "$prompt: " value
  done
  printf '%s' "$value"
}

read_secret() {
  local prompt="$1"
  local value=""
  while [ -z "$value" ]; do
    read -r -s -p "$prompt: " value
    echo
  done
  printf '%s' "$value"
}

copy_or_download_sync_script() {
  mkdir -p "$INSTALL_DIR"
  chmod 700 "$INSTALL_DIR"

  if [ -f "./$SCRIPT_NAME" ]; then
    cp "./$SCRIPT_NAME" "$INSTALL_DIR/$SCRIPT_NAME"
  else
    sync_script_url="${SYNC_SCRIPT_URL:-$DEFAULT_SYNC_SCRIPT_URL}"
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$sync_script_url" -o "$INSTALL_DIR/$SCRIPT_NAME"
    elif command -v wget >/dev/null 2>&1; then
      wget -qO "$INSTALL_DIR/$SCRIPT_NAME" "$sync_script_url"
    else
      echo "未找到本地 $SCRIPT_NAME 时，需要安装 curl 或 wget。"
      exit 1
    fi
  fi

  chmod 700 "$INSTALL_DIR/$SCRIPT_NAME"
  chown root:root "$INSTALL_DIR" "$INSTALL_DIR/$SCRIPT_NAME"
}

install_sync() {
  need_root

  if ! command -v python3 >/dev/null 2>&1; then
    echo "需要先安装 python3。"
    exit 1
  fi

  echo "请输入 Komari 信息"
  komari_url="$(read_required "Komari 地址，例如 https://example.com")"
  komari_api_key="$(read_secret "Komari API Key")"

  echo
  echo "请输入 AkileCloud 信息"
  akile_client_id="$(read_required "Akile Client ID")"
  akile_client_secret="$(read_secret "Akile Client Secret")"

  rmb_symbol="$(printf '\302\245')"
  read -r -p "货币 [${rmb_symbol}]: " komari_currency
  komari_currency="${komari_currency:-$rmb_symbol}"

  read -r -p "同步间隔 [${DEFAULT_INTERVAL}]: " sync_interval
  sync_interval="${sync_interval:-$DEFAULT_INTERVAL}"

  copy_or_download_sync_script

  {
    printf 'AKILE_CLIENT_ID=%s\n' "$akile_client_id"
    printf 'AKILE_CLIENT_SECRET=%s\n' "$akile_client_secret"
    printf 'KOMARI_URL=%s\n' "$komari_url"
    printf 'KOMARI_API_KEY=%s\n' "$komari_api_key"
    printf 'KOMARI_CURRENCY=%s\n' "$komari_currency"
  } >"$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
  chown root:root "$INSTALL_DIR/.env"

  cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Sync AkileCloud billing data to Komari
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/${SCRIPT_NAME} --apply
EOF

  cat >"$TIMER_FILE" <<EOF
[Unit]
Description=Run AkileCloud to Komari billing sync

[Timer]
OnBootSec=10min
OnUnitActiveSec=${sync_interval}
RandomizedDelaySec=5min
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF

  chmod 644 "$SERVICE_FILE" "$TIMER_FILE"
  chown root:root "$SERVICE_FILE" "$TIMER_FILE"

  python3 -m py_compile "$INSTALL_DIR/$SCRIPT_NAME"
  systemctl daemon-reload
  systemctl enable --now "${SERVICE_NAME}.timer"

  echo
  echo "安装完成，正在立即执行一次同步..."
  systemctl start "${SERVICE_NAME}.service"
  systemctl --no-pager status "${SERVICE_NAME}.service" || true
  systemctl list-timers "${SERVICE_NAME}.timer" --no-pager
}

uninstall_sync() {
  need_root

  systemctl disable --now "${SERVICE_NAME}.timer" >/dev/null 2>&1 || true
  rm -f "$SERVICE_FILE" "$TIMER_FILE"
  systemctl daemon-reload
  rm -rf "$INSTALL_DIR"

  echo "已卸载 ${SERVICE_NAME}。"
}

main() {
  echo "AkileCloud to Komari Sync"
  echo "1.安装"
  echo "2.卸载"
  read -r -p "请选择 [1/2]: " choice

  case "$choice" in
    1) install_sync ;;
    2) uninstall_sync ;;
    *) echo "无效选择。"; exit 1 ;;
  esac
}

main "$@"
