# OnKernel live-key verification — paste to the checking AI

The OnKernel API keys were FULLY ROTATED on 2026-09-26. Any key from before that
(git history, onk_key_status.json, onk_*.json strays, old fleet file) is banned and
returns 403 "Organization plan is canceled or unpaid". Those files are deleted.

## Where the 101 LIVE keys are

Repo: crucifix-cray/automation-toolkit, branch main, fresh pull.
Registry: finals/onk_fleet.json → field "key" (rebuilt post-rotation, 0 stale).
Per-account files (101 total, field "api_key"), local absolute paths on this machine:

/home/alan/Documents/railways/finals/sessions/onk-k01-4a827deceb/session.json
/home/alan/Documents/railways/finals/sessions/onk-k03-12a584d48d/session.json
/home/alan/Documents/railways/finals/sessions/onk-k03-3e2f378c43/session.json
/home/alan/Documents/railways/finals/sessions/onk-k04-11b7b92c51/session.json
/home/alan/Documents/railways/finals/sessions/onk-k04-75aae68002/session.json
/home/alan/Documents/railways/finals/sessions/onk-k04-8c8ab3e397/session.json
/home/alan/Documents/railways/finals/sessions/onk-k05-de0e2ca473/session.json
/home/alan/Documents/railways/finals/sessions/onk-k07-3cb123d6c6/session.json
/home/alan/Documents/railways/finals/sessions/onk-k07-7cab0d2f25/session.json
/home/alan/Documents/railways/finals/sessions/onk-k08-bf1824574f/session.json
/home/alan/Documents/railways/finals/sessions/onk-k09-31ffd65709/session.json
/home/alan/Documents/railways/finals/sessions/onk-k10-409e4e8c92/session.json
/home/alan/Documents/railways/finals/sessions/onk-k12-ceb13a5d62/session.json
/home/alan/Documents/railways/finals/sessions/onk-k13-43a361ea66/session.json
/home/alan/Documents/railways/finals/sessions/onk-k14-f683d8e495/session.json
/home/alan/Documents/railways/finals/sessions/onk-k15-29ee754cf5/session.json
/home/alan/Documents/railways/finals/sessions/onk-k16-6db741ae21/session.json
/home/alan/Documents/railways/finals/sessions/onk-k17-5b7778edc0/session.json
/home/alan/Documents/railways/finals/sessions/onk-k18-50acad5545/session.json
/home/alan/Documents/railways/finals/sessions/onk-k21-6eedfc8254/session.json
/home/alan/Documents/railways/finals/sessions/onk-k22-1e2e794975/session.json
/home/alan/Documents/railways/finals/sessions/onk-k22-d1a1907988/session.json
/home/alan/Documents/railways/finals/sessions/onk-k25-8208e5ace8/session.json
/home/alan/Documents/railways/finals/sessions/onk-k26-4d68b36d8a/session.json
/home/alan/Documents/railways/finals/sessions/onk-k26-94e545b543/session.json
/home/alan/Documents/railways/finals/sessions/onk-k28-2a899e96a8/session.json
/home/alan/Documents/railways/finals/sessions/onk-k28-9996e30093/session.json
/home/alan/Documents/railways/finals/sessions/onk-k29-0fa7aa6637/session.json
/home/alan/Documents/railways/finals/sessions/onk-k30-15bc6eed7d/session.json
/home/alan/Documents/railways/finals/sessions/onk-k33-b17b2369a1/session.json
/home/alan/Documents/railways/finals/sessions/onk-k34-7f60d48f26/session.json
/home/alan/Documents/railways/finals/sessions/onk-k35-9881aeb4b6/session.json
/home/alan/Documents/railways/finals/sessions/onk-k36-0037f28fb5/session.json
/home/alan/Documents/railways/finals/sessions/onk-k37-810633167e/session.json
/home/alan/Documents/railways/finals/sessions/onk-k39-37bc5d73c2/session.json
/home/alan/Documents/railways/finals/sessions/onk-k41-cb9279c496/session.json
/home/alan/Documents/railways/finals/sessions/onk-k43-a9512110fa/session.json
/home/alan/Documents/railways/finals/sessions/onk-k44-28882339e0/session.json
/home/alan/Documents/railways/finals/sessions/onk-k44-6b0dda48d8/session.json
/home/alan/Documents/railways/finals/sessions/onk-k45-b177c76d3e/session.json
/home/alan/Documents/railways/finals/sessions/onk-k46-3fd7377ed1/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-04b855c4cc/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-06f0cc3792/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-0a809cf91f/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-0b64aae501/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-100adbd119/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-1041731ff6/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-10aaabc667/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-15e3220460/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-17cbefb24f/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-194e8b5c6d/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-1a09d9e177/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-1ad6773c24/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-1be1f4856b/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-1dfe3d4d30/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-1f48b75e52/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-209ee32ce7/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-327ca12f3a/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-35921bac29/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-39bd4dd9ef/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-3ae409c22b/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-3fda084d9b/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-3ff697a52d/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-42cb5eea91/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-437cd90bb8/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-44320c494b/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-48b74bcd02/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-4ac528d6d4/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-4ce463a405/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-52e2808379/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-5439c51151/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-578c37072b/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-59710b54ce/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-5cb66c6275/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-5db610d77a/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-609b93f7b3/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-62ff7946e9/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-6451a240c4/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-650624fca2/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-67f9f6d152/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-6869f2d086/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-6f91879107/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-73f0c15015/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-78b9ce809d/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-796d19306f/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-79d6dec204/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-7b26ff5210/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-8245340799/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-83d945d926/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-869b669934/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-8943dc7cc7/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-8cd269a28a/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-9dc419c406/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-9fffd723aa/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-b1bcf0718b/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-bc8314c7f7/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-c21f0f9bd0/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-c8c79794d1/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-e1268be722/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-f263ad13b5/session.json
/home/alan/Documents/railways/finals/sessions/onk-onk-f57225e99f/session.json

Portable equivalents: same list under repo root, i.e.

finals/sessions/onk-k01-4a827deceb/session.json
finals/sessions/onk-k03-12a584d48d/session.json
finals/sessions/onk-k03-3e2f378c43/session.json
  ... (all 101 follow the same pattern: finals/sessions/onk-*/session.json)

Fast extraction (repo root):
  for f in finals/sessions/onk-*/session.json; do jq -r .api_key "$f"; done

## How to verify (only this counts)

  curl -X POST https://api.onkernel.com/browsers \
    -H "Authorization: Bearer <key>" -H "Content-Type: application/json" \
    -d '{"session_name":"verify","live_url":true}'

  → HTTP 200 + cdp_ws_url = WORKING. Delete the test browser after:
    curl -X DELETE https://api.onkernel.com/browsers/<id> -H "Authorization: Bearer <key>"
  → 403 plan/canceled = stale pre-rotation key, discard it, it is not live material.
  → 429 = YOU are throttling yourself (too much concurrency). Back off, retry
    sequentially (max 3 parallel). It is not the key.

Expected: 101/101 return 200. Probe max 3 at a time, one browser per key,
delete each test browser immediately. Do not report any key as dead without
pasting its exact HTTP code + response body.
