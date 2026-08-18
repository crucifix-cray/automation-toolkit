# Chimera bridge

`chimera-bridge/` is a small TCP forwarding service designed to run on
Railway (or a VPS via systemd). It proxies connections to Monero pool
endpoints and gates access with shared auth keys.

## Files

| File | Purpose |
|---|---|
| `bridge.py` | Main server: TLS-capable TCP forwarder with key auth |
| `bridge-test.py` | Standalone test harness for the bridge |
| `test_client.py` | Client-side test that connects and sends traffic |
| `requirements.txt` | Python deps |
| `Procfile` / `railway.json` | Railway run configuration |
| `deploy.sh` | VPS/systemd deployment script |
| `systemd/chimera-bridge.service` | systemd unit for the VPS install |
| `config.example.json` | Config template (auth keys are placeholders) |
| `README.md` | Bridge-specific usage |

## Configuration

Copy `config.example.json` to `config.json` and set:

- `auth_keys` – shared secrets clients must present (put real keys here,
  never commit them).
- `pools` – mapping of pool name -> `host:port` to forward to.
- `ssl.enabled` – terminate TLS on the bridge port (set `false` if the
  upstream/proxy already terminates, as in the Railway setup).
- `limits.max_clients` – connection cap.

## Deploying

Railway:

```bash
railway up        # uses Procfile / railway.json from the repo
```

VPS with systemd:

```bash
sudo ./deploy.sh  # installs deps, copies unit, starts the service
```

## Security notes

- The committed config is a template; the real `config.json` lives only on
  the host (and in local session dirs, which are git-ignored).
- If the bridge is exposed publicly, `auth_keys` are the only gate – rotate
  them and use `ssl.enabled: true` in production.
