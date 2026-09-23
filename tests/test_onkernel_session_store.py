import asyncio
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "onkernel"))

from session_store import (  # noqa: E402
    atomic_write_json,
    backup_session_bundle,
    save_latest_pointer,
    save_session_bundle,
)


class FakeContext:
    async def cookies(self):
        return [{"name": "session", "value": "secret"}]

    async def storage_state(self):
        return {"cookies": [], "origins": [{"origin": "https://example.test"}]}


class SessionStoreTests(unittest.TestCase):
    def test_atomic_bundle_backup_and_latest_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "onk_123.json"
            account = {
                "email": "account@example.test",
                "password": "do-not-put-in-pointer",
                "api_key": "sk_example",
                "status": "ready",
            }

            asyncio.run(save_session_bundle(session, account, FakeContext()))
            save_latest_pointer(session, account)
            backup = backup_session_bundle(session, "test")

            self.assertEqual(json.loads(session.read_text()), account)
            self.assertTrue((Path(tmp) / "onk_123.cookies.json").exists())
            self.assertTrue((Path(tmp) / "onk_123.storage.json").exists())
            self.assertTrue((backup / "manifest.json").exists())
            self.assertTrue((backup / "onk_123.json").exists())

            latest = json.loads((Path(tmp) / "latest_onk.json").read_text())
            self.assertEqual(latest["email"], account["email"])
            self.assertNotIn("password", latest)
            self.assertEqual(stat.S_IMODE(session.stat().st_mode), 0o600)

    def test_atomic_write_replaces_complete_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"
            atomic_write_json(path, {"generation": 1})
            atomic_write_json(path, {"generation": 2, "complete": True})
            self.assertEqual(
                json.loads(path.read_text()),
                {"generation": 2, "complete": True},
            )


if __name__ == "__main__":
    unittest.main()
