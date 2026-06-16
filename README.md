# AkileCloud to Komari Sync

Sync AkileCloud server billing data to Komari nodes by matching node names.

No API keys or secrets are stored in this repository. The installer prompts for
credentials and writes them only to `/opt/akile-komari-sync/.env` on your VPS
with `600` permissions.

## Features

- Sync Akile `due_time` to Komari `expired_at`
- Sync Akile `auto_renew` to Komari `auto_renewal`
- Sync Akile `price` to Komari `price`
- Convert free plans from Akile `price = 0` to Komari `price = -1`
- Use RMB currency symbol by default
- Convert Akile billing cycle to Komari days:
  - `1` month -> `30`
  - `3` months -> `92`
  - `12` months -> `365`
  - `24` months -> `730`
- Convert Akile `flow` in GB to Komari `traffic_limit` in bytes
- Set Komari `traffic_limit_type` to `sum`
- Store Akile due dates as China-time wall-clock values to avoid one-day date drift
- Run automatically with a systemd timer, default every 1 hour

## Install

Clone this repository on the Komari VPS, then run:

```bash
sudo bash install.sh
```

The menu will show:

```text
1. Install
2. Uninstall
```

Choose `1` and enter values in this order:

1. Komari URL
2. Komari API key
3. Akile Client ID
4. Akile Client Secret
5. Currency, optional, defaults to RMB
6. Sync interval, optional, defaults to `1h`

Node matching is name-based. The Akile machine name and Komari node name should
be the same.

## Publish To GitHub

From this folder:

```bash
git init
git add .gitignore .env.example README.md install.sh sync_akile_komari.py
git commit -m "Initial AkileCloud to Komari sync"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

Only the template `.env.example` is tracked. Do not commit a real `.env` file.

## Uninstall

Run:

```bash
sudo bash install.sh
```

Choose `2`. This removes:

- `/opt/akile-komari-sync`
- `/etc/systemd/system/akile-komari-sync.service`
- `/etc/systemd/system/akile-komari-sync.timer`

It does not modify Komari itself.

## Manual Run

Preview only:

```bash
cd /opt/akile-komari-sync
set -a
. ./.env
set +a
python3 sync_akile_komari.py
```

Apply updates:

```bash
systemctl start akile-komari-sync.service
```

Check schedule and logs:

```bash
systemctl list-timers akile-komari-sync.timer --no-pager
journalctl -u akile-komari-sync.service -n 50 --no-pager
```
