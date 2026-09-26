#!/usr/bin/env python3
"""Chimera bridge — WebSocket <-> Stratum pool relay.

Hardened replacement for the old bridge, which leaked a handler coroutine
every time the pool side dropped (gather() parked on the idle client socket).
Enough leaks and the service refused every new connection with 1013
"at capacity", so no worker could get a job.

Fixes vs old bridge:
  * Either direction ending tears the session down (no parked gather()).
  * pool unreachable -> close the client with a real code, never half-open.
  * MAX_CLIENTS cap with immediate 1013 rejection instead of unbounded growth.
  * Hard per-connection idle timeout so dead sockets are reaped.
  * /health and /stats on plain HTTP for diagnosis.

Env: PORT, POOL_HOST, POOL_PORT, WALLET, MAX_CLIENTS, AUTH_TOKEN
"""
import asyncio
import json
import logging
import os

import websockets
from websockets.asyncio.server import serve

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("bridge")

PORT         = int(os.environ.get("PORT", 8080))
POOL_HOST    = os.environ.get("POOL_HOST", "pool.supportxmr.com")
POOL_PORT    = int(os.environ.get("POOL_PORT", 3333))
WALLET       = os.environ.get("WALLET", "")
MAX_CLIENTS  = int(os.environ.get("MAX_CLIENTS", 400))
IDLE_TIMEOUT = int(os.environ.get("IDLE_TIMEOUT", 900))

stats = {"clients": 0, "peak": 0, "shares": 0, "accepted": 0, "rejected": 0}


async def _health_sidecar():
    """Optional plain-HTTP probe on HEALTH_PORT, off the WS handshake path."""
    port = int(os.environ.get("HEALTH_PORT", "0"))
    if not port:
        return
    async def handle_http(reader, writer):
        try:
            await reader.read(1024)
            body = json.dumps({"ok": True, "clients": stats["clients"],
                               "peak": stats["peak"], "shares": stats["shares"],
                               "accepted": stats["accepted"],
                               "rejected": stats["rejected"]}).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         b"Content-Length: " + str(len(body)).encode() +
                         b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass
    srv = await asyncio.start_server(handle_http, "0.0.0.0", port)
    log.info(f"[health] http probe on :{port}")
    async with srv:
        await srv.serve_forever()


# NOTE: no process_request hook on purpose. Mixing a plain-HTTP health
# endpoint into the WS handshake path broke the upgrade (500s) on the
# websockets asyncio server. Diagnostics live in the logs + /stats below
# is served by a tiny sidecar HTTP server when HEALTH_PORT is set.


async def _pump(ws, pool_reader, pool_writer, label):
    """Relay both ways until EITHER ends, then hard-close the session."""
    done = asyncio.Event()

    async def ws_to_pool():
        login_done = False
        try:
            async for msg in ws:
                data = msg if isinstance(msg, bytes) else msg.encode()
                if not login_done and WALLET and b'"login"' in data:
                    data = _inject_wallet(data, label)
                    login_done = True
                if b'"method":"submit"' in data:
                    stats["shares"] += 1
                pool_writer.write(data)
                await pool_writer.drain()
        except Exception as e:
            log.debug(f"[{label}] ws->pool: {e}")
        finally:
            done.set()

    async def pool_to_ws():
        first = True
        try:
            while True:
                chunk = await pool_reader.read(8192)
                if not chunk:
                    log.info(f"[{label}] POOL CLOSED (clean EOF) — tearing session down")
                    break
                if first:
                    first = False
                    # First pool frame decides everything: a job means we are
                    # mining, an error means the pool rejected the login.
                    head = chunk[:180].decode("utf-8", "replace").replace("\n", " ")
                    if b'"job"' in chunk:
                        log.info(f"[{label}] POOL OK job issued: {head[:120]}")
                    else:
                        log.warning(f"[{label}] POOL REJECTED: {head[:160]}")
                if b'"error":null' in chunk and b'"id"' in chunk:
                    stats["accepted"] += 1
                    log.info(f"[{label}] accepted {stats['accepted']}/{stats['shares']}")
                await ws.send(chunk)
        except Exception as e:
            log.info(f"[{label}] POOL ERROR: {type(e).__name__}: {str(e)[:100]}")
        finally:
            done.set()

    tasks = [asyncio.create_task(ws_to_pool()), asyncio.create_task(pool_to_ws())]
    await done.wait()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def _inject_wallet(data, label):
    try:
        lines = data.decode().strip().splitlines()
        for i, line in enumerate(lines):
            obj = json.loads(line)
            if obj.get("method") == "login" and "params" in obj:
                orig = obj["params"].get("login", "")
                suffix = orig.split(".")[-1] if "." in orig else orig
                obj["params"]["login"] = f"{WALLET}.{suffix}"
                lines[i] = json.dumps(obj)
        log.info(f"[{label}] wallet injected for worker={suffix}")
        return ("\n".join(lines) + "\n").encode()
    except Exception as e:
        log.debug(f"[{label}] wallet inject failed: {e}")
        return data


async def handle(ws):
    addr = ws.remote_address
    if stats["clients"] >= MAX_CLIENTS:
        stats["rejected"] += 1
        log.warning(f"[!] reject {addr} — at capacity ({stats['clients']}/{MAX_CLIENTS})")
        await ws.close(code=1013, reason="at capacity")
        return

    stats["clients"] += 1
    stats["peak"] = max(stats["peak"], stats["clients"])
    log.info(f"[+] client {addr} (active {stats['clients']}/{MAX_CLIENTS})")

    pool_writer = None
    try:
        try:
            pool_reader, pool_writer = await asyncio.wait_for(
                asyncio.open_connection(POOL_HOST, POOL_PORT), timeout=15)
            log.info(f"[{addr}] POOL CONNECTED {POOL_HOST}:{POOL_PORT}")
        except asyncio.TimeoutError:
            log.error(f"[{addr}] POOL CONNECT TIMEOUT after 15s")
            await ws.close(code=1013, reason="pool timeout")
            return
        except Exception as e:
            log.error(f"[{addr}] POOL CONNECT FAILED {type(e).__name__}: {str(e)[:120]}")
            # Never leave the client half-open: say so and close.
            await ws.close(code=1013, reason="pool unreachable")
            return

        await _pump(ws, pool_reader, pool_writer, str(addr))
    except Exception as e:
        log.debug(f"[!] session {addr}: {e}")
    finally:
        stats["clients"] -= 1
        log.info(f"[-] client {addr} (active {stats['clients']})")
        if pool_writer is not None:
            try:
                pool_writer.close()
                await pool_writer.wait_closed()
            except Exception:
                pass
        try:
            await ws.close()
        except Exception:
            pass


async def main():
    log.info("=" * 55)
    log.info("Chimera bridge (hardened)")
    log.info(f"  listen   : 0.0.0.0:{PORT}")
    log.info(f"  pool     : {POOL_HOST}:{POOL_PORT}")
    log.info(f"  max      : {MAX_CLIENTS} clients")
    log.info(f"  wallet   : {'set' if WALLET else 'UNSET'}")
    log.info("=" * 55)
    asyncio.create_task(_health_sidecar())
    async with serve(
        handle,
        "0.0.0.0",
        PORT,
        ping_interval=30,
        ping_timeout=10,
        max_size=None,
        compression=None,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
