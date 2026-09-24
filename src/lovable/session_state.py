#!/usr/bin/env python3
"""Shared Lovable session persistence: cookies + localStorage + Firebase IndexedDB.

The Firebase refresh_token lives in indexedDB (`firebaseLocalStorageDb`).
Without it, expired access tokens force a full email/password/TOTP login.
Always call `save_full_state` after a successful login / signup / rescue.

Auth revive (no password): `revive_via_refresh_token` — mint access token via
Google's securetoken API, inject IDB through a virgin browser context
init-script (Lovable SPA locks IDB; in-page put/evaluate hangs), copy cookies back.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _has_refresh(idb_data: list) -> bool:
    for r in idb_data or []:
        if not isinstance(r, dict):
            continue
        v = r.get("value")
        if isinstance(v, dict) and (v.get("stsTokenManager") or {}).get("refreshToken"):
            return True
    return False


def synthesize_idb_keys(idb_data: list) -> list:
    """Ensure each Firebase auth record has fkey `firebase:authUser:{apiKey}:{appName}`."""
    for r in idb_data or []:
        if not isinstance(r, dict):
            continue
        if r.get("key") or r.get("fkey"):
            continue
        v = r.get("value") if isinstance(r.get("value"), dict) else None
        if v and v.get("apiKey"):
            r["key"] = f"firebase:authUser:{v['apiKey']}:{v.get('appName') or '[DEFAULT]'}"
    return idb_data


async def extract_indexeddb(page) -> list[dict[str, Any]]:
    """Read firebaseLocalStorageDb → list of {store, key, value} (key = fkey)."""
    data = await page.evaluate("""async () => {
        return new Promise((resolve) => {
            try {
                const req = indexedDB.open('firebaseLocalStorageDb');
                req.onsuccess = () => {
                    const db = req.result;
                    const stores = Array.from(db.objectStoreNames || []);
                    if (!stores.length) { resolve([]); return; }
                    const tx = db.transaction(stores, 'readonly');
                    const out = [];
                    let pending = stores.length;
                    stores.forEach(sn => {
                        try {
                            const rq = tx.objectStore(sn).getAll();
                            rq.onsuccess = () => {
                                (rq.result || []).forEach(r => {
                                    let key = r.fkey || r.key || null;
                                    const value = r.value !== undefined ? r.value : r;
                                    if (!key && value && value.apiKey) {
                                        key = 'firebase:authUser:' + value.apiKey + ':' + (value.appName || '[DEFAULT]');
                                    }
                                    out.push({ store: sn, key, value });
                                });
                                if (--pending === 0) resolve(out);
                            };
                            rq.onerror = () => { if (--pending === 0) resolve(out); };
                        } catch (e) { if (--pending === 0) resolve(out); }
                    });
                };
                req.onerror = () => resolve([]);
            } catch (e) { resolve([]); }
        });
    }""")
    return synthesize_idb_keys(data or [])


async def save_full_state(context, page, session_dir, *, retries: int = 4, wait_ms: int = 2500) -> bool:
    """Persist cookies + localStorage + IndexedDB.

    Retries IndexedDB a few times so Firebase can finish writing the refresh token
    after login. Returns True iff a refresh_token was saved.
    Never clobbers a good on-disk refresh_token with an empty extract.
    """
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    log = print

    # 1) cookies
    fresh_cookies = await context.cookies()
    (session_dir / "cookies.json").write_text(json.dumps(fresh_cookies, indent=2))
    log(f"   ✅ Saved {len(fresh_cookies)} cookies")

    # 2) localStorage
    try:
        ls_data = await page.evaluate("""() => {
            const out = {};
            try {
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    out[k] = localStorage.getItem(k);
                }
            } catch (e) {}
            return out;
        }""")
        (session_dir / "localstorage.json").write_text(json.dumps(ls_data, indent=2))
        log(f"   ✅ Saved localStorage ({len(ls_data)} keys)")
    except Exception as e:
        log(f"   ⚠️  localStorage save failed: {e}")

    # 3) IndexedDB — must contain Firebase refresh_token
    idb_data: list = []
    has_refresh = False
    for attempt in range(1, retries + 1):
        try:
            if "lovable.dev" not in (page.url or ""):
                try:
                    await page.goto(
                        "https://lovable.dev/dashboard",
                        timeout=20000,
                        wait_until="domcontentloaded",
                    )
                except Exception:
                    pass
            idb_data = await extract_indexeddb(page) or []
            has_refresh = _has_refresh(idb_data)
            if has_refresh:
                break
            log(f"   ⏳ IndexedDB attempt {attempt}/{retries}: no refresh_token yet — wait {wait_ms}ms")
            await page.wait_for_timeout(wait_ms)
        except Exception as e:
            log(f"   ⚠️  IndexedDB read failed (attempt {attempt}): {e}")
            await page.wait_for_timeout(wait_ms)

    idb_path = session_dir / "indexeddb.json"
    if (not idb_data or not has_refresh) and idb_path.exists():
        try:
            prev = json.loads(idb_path.read_text())
            if _has_refresh(prev) and not has_refresh:
                log("   ⚠️  IndexedDB extract empty/missing RT — keeping existing indexeddb.json")
                return True
        except Exception:
            pass

    synthesize_idb_keys(idb_data)
    idb_path.write_text(json.dumps(idb_data, indent=2))
    if has_refresh:
        log(f"   ✅ Saved IndexedDB ({len(idb_data)} records, refresh_token=YES)")
    else:
        log(f"   ❌ Saved IndexedDB ({len(idb_data)} records, refresh_token=MISSING)")
    return has_refresh


def _mint_access_token(idb_data: list) -> bool:
    """Update accessToken in-place via Google securetoken API. Returns True on success."""
    synthesize_idb_keys(idb_data)
    user = None
    for r in idb_data:
        v = r.get("value") if isinstance(r, dict) else None
        if isinstance(v, dict) and (v.get("stsTokenManager") or {}).get("refreshToken"):
            user = v
            break
    if not user:
        return False
    stm = user["stsTokenManager"]
    api_key = user.get("apiKey") or ""
    body = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": stm["refreshToken"]}
    ).encode()
    req = urllib.request.Request(
        f"https://securetoken.googleapis.com/v1/token?key={api_key}",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        tok = json.loads(resp.read().decode())
    if not tok.get("access_token"):
        return False
    stm["accessToken"] = tok["access_token"]
    stm["expirationTime"] = int(time.time() * 1000) + int(tok.get("expires_in", 3600)) * 1000
    if tok.get("refresh_token"):
        stm["refreshToken"] = tok["refresh_token"]
    return True


def _idb_init_script(idb_data: list) -> str:
    return (
        "(() => {\n"
        f"  const records = {json.dumps(idb_data)};\n"
        "  window.__chimeraIdbReady = new Promise((resolve) => {\n"
        "    try {\n"
        "      const openReq = indexedDB.open('firebaseLocalStorageDb');\n"
        "      openReq.onupgradeneeded = () => {\n"
        "        try {\n"
        "          const db = openReq.result;\n"
        "          if (!db.objectStoreNames.contains('firebaseLocalStorage'))\n"
        "            db.createObjectStore('firebaseLocalStorage', {keyPath: 'fkey'});\n"
        "        } catch (e) {}\n"
        "      };\n"
        "      openReq.onerror = () => resolve(false);\n"
        "      openReq.onsuccess = () => {\n"
        "        try {\n"
        "          const db = openReq.result;\n"
        "          if (!db.objectStoreNames.contains('firebaseLocalStorage')) {\n"
        "            resolve(false); return;\n"
        "          }\n"
        "          const tx = db.transaction('firebaseLocalStorage', 'readwrite');\n"
        "          const store = tx.objectStore('firebaseLocalStorage');\n"
        "          records.forEach(r => {\n"
        "            try { store.put({fkey: r.key || r.fkey, value: r.value}); } catch (e) {}\n"
        "          });\n"
        "          tx.oncomplete = () => resolve(true);\n"
        "          tx.onerror = () => resolve(false);\n"
        "        } catch (e) { resolve(false); }\n"
        "      };\n"
        "    } catch (e) { resolve(false); }\n"
        "  });\n"
        "})();"
    )


async def revive_via_refresh_token(
    page,
    session_dir,
    *,
    target_url: str = "https://lovable.dev/dashboard",
) -> bool:
    """Auth revive without password — proven local path for cell auth walls.

    1) Read disk indexeddb.json (must have refresh_token + real fkey)
    2) Mint new access_token via Google API (Python — not page.evaluate)
    3) Virgin browser context + init-script IDB inject (SPA locks IDB otherwise)
    4) Copy cookies into caller's context and navigate
    """
    session_dir = Path(session_dir)
    idb_file = session_dir / "indexeddb.json"
    log = print
    if not idb_file.exists():
        log("   ⚠️  No indexeddb.json — cannot refresh_token revive")
        return False
    try:
        idb_data = json.loads(idb_file.read_text())
    except Exception as e:
        log(f"   ⚠️  indexeddb.json read failed: {e}")
        return False
    synthesize_idb_keys(idb_data)
    if not _has_refresh(idb_data):
        log("   ⚠️  indexeddb.json has no refresh_token")
        return False
    try:
        if not _mint_access_token(idb_data):
            log("   ⚠️  Google refresh_token API failed")
            return False
        log("   ✅ Google refresh_token → new access_token OK")
    except Exception as e:
        log(f"   ⚠️  Google refresh error: {e}")
        return False
    try:
        idb_file.write_text(json.dumps(idb_data, indent=2))
    except Exception:
        pass

    browser = page.context.browser
    if browser is None:
        log("   ⚠️  No browser handle for virgin context")
        return False
    fresh_ctx = None
    try:
        fresh_ctx = await browser.new_context()
        await fresh_ctx.add_init_script(_idb_init_script(idb_data))
        fresh = await fresh_ctx.new_page()
        await fresh.goto(target_url, timeout=40000, wait_until="domcontentloaded")
        try:
            ready = await asyncio.wait_for(
                fresh.evaluate("() => window.__chimeraIdbReady"),
                timeout=8,
            )
            log(f"   IDB init inject ready={ready}")
        except Exception:
            pass
        await asyncio.sleep(4)
        url = (fresh.url or "").lower()
        if "/login" in url or "/auth" in url:
            try:
                await fresh.reload(timeout=40000, wait_until="domcontentloaded")
                await asyncio.sleep(4)
            except Exception:
                pass
        url = (fresh.url or "").lower()
        if "/login" in url or "/auth" in url:
            log("   ⚠️  Refresh ran but still on auth wall")
            return False
        cookies = await fresh_ctx.cookies()
        (session_dir / "cookies.json").write_text(json.dumps(cookies, indent=2))
        log(f"   ✅ Auth revived via refresh_token — saved {len(cookies)} cookies")
        try:
            await page.context.clear_cookies()
        except Exception:
            pass
        try:
            await page.context.add_cookies(cookies)
        except Exception as e:
            log(f"   ⚠️  cookie copy soft-fail: {e}")
        try:
            await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
        except Exception:
            pass
        return True
    except Exception as e:
        log(f"   ⚠️  virgin-context revive failed: {type(e).__name__}: {e}")
        return False
    finally:
        if fresh_ctx is not None:
            try:
                await fresh_ctx.close()
            except Exception:
                pass
