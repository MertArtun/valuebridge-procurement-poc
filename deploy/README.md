# Public demo deployment

Runs the PoC behind Caddy at
[valuebridge.62-238-40-66.sslip.io](https://valuebridge.62-238-40-66.sslip.io)
with `VALUEBRIDGE_DEMO_MODE=1`: every response is marked `noindex, nofollow`
and `/api/**` is rate limited per client IP (30 requests, refilling at 30 per
minute). Requires Docker Compose v2.24 or newer for the `!override` merge tag.

## Host layout

The overlay resolves `../` against the clone directory, so the host must look
exactly like this:

```
~/valuebridge/
├── app/                     # this repository
├── .env                     # runtime environment, never committed
├── policy_embeddings.json   # optional hybrid retrieval index
└── caddy-data/              # issued certificates, survives the nightly reset
```

```bash
mkdir -p ~/valuebridge/caddy-data
git clone <repo-url> ~/valuebridge/app
cp ~/valuebridge/app/.env.example ~/valuebridge/.env   # then fill it in
```

`.env` must exist or Compose refuses to start. `policy_embeddings.json` must
also exist before the first `up`, otherwise Docker creates a directory in its
place; an empty index is fine because policy retrieval falls back to lexical
scoring. Build it with `python scripts/embed_policy_sections.py` and copy the
generated `data/policy_embeddings.json` to `~/valuebridge/`.

Point the DNS name at the host before starting: `sslip.io` resolves
`valuebridge.62-238-40-66.sslip.io` to `62.238.40.66` on its own, so only
ports 80 and 443 have to be reachable for Caddy to complete the ACME challenge.

## Start the stack

```bash
cd ~/valuebridge/app
docker compose -p valuebridge -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

The application listens on `127.0.0.1:8090` for local smoke tests; external
traffic reaches it only through Caddy, which is what makes the rate limiter's
`X-Forwarded-For` client key trustworthy.

## systemd (user units)

```bash
loginctl enable-linger "$USER"
mkdir -p ~/.config/systemd/user
cp ~/valuebridge/app/deploy/valuebridge-demo*.service ~/.config/systemd/user/
cp ~/valuebridge/app/deploy/valuebridge-demo-reset.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now valuebridge-demo.service
systemctl --user enable --now valuebridge-demo-reset.timer
systemctl --user list-timers valuebridge-demo-reset.timer
```

`valuebridge-demo-reset.timer` fires every day at 03:00 Europe/Istanbul and
recreates the stack with empty databases, so the public demo always opens on
the seeded scenario. The timezone suffix needs systemd 252 or newer; on older
releases drop it from `OnCalendar=` and set the host clock with
`timedatectl set-timezone Europe/Istanbul`.

Lingering is what keeps the user units running while nobody is logged in. The
services carry no `Restart=` directive because every container declares
`restart: unless-stopped`, which also brings the stack back after a reboot.

## Smoke test

```bash
curl -fsS https://valuebridge.62-238-40-66.sslip.io/health
curl -sI https://valuebridge.62-238-40-66.sslip.io/ | grep -i x-robots-tag
```

Expected: `{"status":"ok"}` and `x-robots-tag: noindex, nofollow`.

Rate limiting, from the host:

```bash
for _ in $(seq 1 35); do
  curl -s -o /dev/null -w '%{http_code} ' \
    -H 'X-Demo-Role: auditor' -H 'X-Demo-User: auditor_user' \
    http://127.0.0.1:8090/api/v1/metrics/summary
done; echo
```

Expected: thirty `200` responses, then `429` with a `Retry-After` header.

## Manual reset

```bash
systemctl --user start valuebridge-demo-reset.service
```
