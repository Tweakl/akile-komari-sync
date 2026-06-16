#!/usr/bin/env python3
"""
Sync AkileCloud VPS billing data to Komari clients by matching names.

Credentials are read from environment variables:
  AKILE_CLIENT_ID
  AKILE_CLIENT_SECRET
  KOMARI_URL
  KOMARI_API_KEY
  KOMARI_CURRENCY optional, defaults to RMB

By default this script is dry-run. Add --apply to update Komari.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request


AKILE_API = "https://api.akile.ai/api/v1"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def request_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body=None):
    data = None
    final_headers = {"User-Agent": "akile-komari-sync/1.0", "Accept": "application/json"}
    if headers:
        final_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        final_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=final_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail[:500]}") from exc


def normalize_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def due_time_to_komari_time(value: int | float) -> str:
    timestamp = value / 1000 if value > 10_000_000_000 else value
    # Komari stores billing timestamps as LocalTime. Writing real UTC can make
    # China-time midnight renewals appear as the previous day, so store the
    # Asia/Shanghai wall-clock time in Komari's normalized "Z" form.
    china_tz = dt.timezone(dt.timedelta(hours=8))
    return dt.datetime.fromtimestamp(timestamp, china_tz).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def fetch_akile_servers(client_id: str, client_secret: str, page_size: int = 100) -> list[dict]:
    servers: list[dict] = []
    page = 1
    total = None
    while True:
        resp = request_json(
            f"{AKILE_API}/api/server/GetServerList",
            method="POST",
            headers={"Api-Client": client_id, "Api-Secret": client_secret},
            body={"page_num": page, "page_size": page_size},
        )
        batch = resp.get("list") or resp.get("data", {}).get("list") or []
        total = resp.get("total", total)
        servers.extend(batch)
        if not batch or len(batch) < page_size or (total is not None and len(servers) >= int(total)):
            break
        page += 1
    return servers


def fetch_komari_clients(komari_url: str, api_key: str) -> list[dict]:
    return request_json(
        f"{komari_url.rstrip('/')}/api/admin/client/list",
        headers={"Authorization": f"Bearer {api_key}"},
    )


def update_komari_client(komari_url: str, api_key: str, uuid: str, expired_at: str, auto_renewal: bool) -> dict:
    return request_json(
        f"{komari_url.rstrip('/')}/api/admin/client/{uuid}/edit",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        body={"expired_at": expired_at, "auto_renewal": auto_renewal},
    )


def update_komari_billing(
    komari_url: str,
    api_key: str,
    uuid: str,
    *,
    expired_at: str,
    auto_renewal: bool,
    price: float,
    currency: str,
    billing_cycle: int,
    traffic_limit: int,
    traffic_limit_type: str,
) -> dict:
    return request_json(
        f"{komari_url.rstrip('/')}/api/admin/client/{uuid}/edit",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        body={
            "expired_at": expired_at,
            "auto_renewal": auto_renewal,
            "price": price,
            "currency": currency,
            "billing_cycle": billing_cycle,
            "traffic_limit": traffic_limit,
            "traffic_limit_type": traffic_limit_type,
        },
    )


def akile_price_to_komari(value) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    if value == 0:
        return -1
    return round(float(value) / 100, 2)


def akile_cycle_to_komari(value) -> int | None:
    if not isinstance(value, int):
        return None
    known_cycles = {
        1: 30,
        3: 92,
        12: 365,
        24: 730,
    }
    if value in known_cycles:
        return known_cycles[value]
    return value * 30


def akile_flow_to_komari(value) -> int | None:
    if not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return int(round(float(value) * 1024 * 1024 * 1024))


def values_equal(old, new) -> bool:
    if isinstance(new, float):
        try:
            return abs(float(old) - new) < 0.001
        except (TypeError, ValueError):
            return False
    return old == new


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync AkileCloud due_time into Komari expired_at by matching names.")
    parser.add_argument("--apply", action="store_true", help="write updates to Komari")
    parser.add_argument("--case-sensitive", action="store_true", help="match names exactly instead of trim/lowercase matching")
    args = parser.parse_args()

    required = {
        "AKILE_CLIENT_ID": os.getenv("AKILE_CLIENT_ID"),
        "AKILE_CLIENT_SECRET": os.getenv("AKILE_CLIENT_SECRET"),
        "KOMARI_URL": os.getenv("KOMARI_URL"),
        "KOMARI_API_KEY": os.getenv("KOMARI_API_KEY"),
    }
    currency = os.getenv("KOMARI_CURRENCY", "\u00a5")
    missing = [key for key, value in required.items() if not value]
    if missing:
        print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
        return 2

    akile_servers = fetch_akile_servers(required["AKILE_CLIENT_ID"], required["AKILE_CLIENT_SECRET"])
    komari_clients = fetch_komari_clients(required["KOMARI_URL"], required["KOMARI_API_KEY"])

    def key(name: str) -> str:
        return name.strip() if args.case_sensitive else normalize_name(name)

    komari_by_name: dict[str, dict] = {}
    duplicate_komari_names: set[str] = set()
    for client in komari_clients:
        name = client.get("name") or ""
        k = key(name)
        if not k:
            continue
        if k in komari_by_name:
            duplicate_komari_names.add(k)
        komari_by_name[k] = client

    matched = 0
    changed = 0
    skipped_duplicate = 0
    unmatched = []

    for server in akile_servers:
        name = server.get("server_re_name") or server.get("server_name") or ""
        k = key(name)
        due_time = server.get("due_time")
        if k in duplicate_komari_names:
            skipped_duplicate += 1
            print(f"SKIP duplicate Komari name: {name}")
            continue
        client = komari_by_name.get(k)
        if not client:
            unmatched.append(name)
            continue
        if not isinstance(due_time, (int, float)):
            print(f"SKIP no due_time: {name}")
            continue

        matched += 1
        expired_at = due_time_to_komari_time(due_time)
        auto_renewal = bool(server.get("auto_renew"))
        price = akile_price_to_komari(server.get("price"))
        billing_cycle = akile_cycle_to_komari(server.get("cycle"))
        traffic_limit = akile_flow_to_komari(server.get("flow"))
        traffic_limit_type = "sum"
        old_expired_at = client.get("expired_at")
        old_auto_renewal = bool(client.get("auto_renewal"))
        old_price = client.get("price")
        old_currency = client.get("currency")
        old_billing_cycle = client.get("billing_cycle")
        old_traffic_limit = client.get("traffic_limit")
        old_traffic_limit_type = client.get("traffic_limit_type")

        billing_fields_ok = price is not None and isinstance(billing_cycle, int)
        traffic_fields_ok = traffic_limit is not None
        needs_update = old_expired_at != expired_at or old_auto_renewal != auto_renewal
        if billing_fields_ok:
            needs_update = (
                needs_update
                or not values_equal(old_price, price)
                or old_currency != currency
                or old_billing_cycle != billing_cycle
            )
        if traffic_fields_ok:
            needs_update = (
                needs_update
                or old_traffic_limit != traffic_limit
                or old_traffic_limit_type != traffic_limit_type
            )

        prefix = "UPDATE" if needs_update else "OK"
        line = (
            f"{prefix} {name}: expired_at {old_expired_at} -> {expired_at}, "
            f"auto_renewal {old_auto_renewal} -> {auto_renewal}"
        )
        if billing_fields_ok:
            line += (
                f", price {old_price} -> {price}, "
                f"currency {old_currency} -> {currency}, "
                f"billing_cycle {old_billing_cycle} -> {billing_cycle}"
            )
        else:
            line += ", billing skipped: missing price or cycle"
        if traffic_fields_ok:
            line += (
                f", traffic_limit {old_traffic_limit} -> {traffic_limit}, "
                f"traffic_limit_type {old_traffic_limit_type} -> {traffic_limit_type}"
            )
        else:
            line += ", traffic skipped: missing flow"
        print(line)
        if args.apply and needs_update:
            if billing_fields_ok and traffic_fields_ok:
                update_komari_billing(
                    required["KOMARI_URL"],
                    required["KOMARI_API_KEY"],
                    client["uuid"],
                    expired_at=expired_at,
                    auto_renewal=auto_renewal,
                    price=price,
                    currency=currency,
                    billing_cycle=billing_cycle,
                    traffic_limit=traffic_limit,
                    traffic_limit_type=traffic_limit_type,
                )
            else:
                update_komari_client(required["KOMARI_URL"], required["KOMARI_API_KEY"], client["uuid"], expired_at, auto_renewal)
            changed += 1

    print()
    print(f"Akile servers: {len(akile_servers)}")
    print(f"Komari clients: {len(komari_clients)}")
    print(f"Matched: {matched}")
    print(f"Changed: {changed if args.apply else 'dry-run'}")
    print(f"Skipped duplicate names: {skipped_duplicate}")
    print(f"Unmatched Akile names: {len(unmatched)}")
    for name in unmatched:
        print(f"  - {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
