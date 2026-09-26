# Script Reorganization Plan

## Current State (From SCRIPT_INVENTORY.md)
- 97 Python scripts scattered across finals/core/ and scripts/
- 25 active/working scripts
- 35 deprecated/old scripts
- 20 testing/experimental scripts
- 17 duplicates in nested Railway directories

## Proposed New Structure

```
automation-toolkit/
├── src/                          # NEW - Active working scripts
│   ├── lovable/                  # Lovable automation
│   │   ├── account_creation.py   # lov-api-effective.py
│   │   ├── remix_inject.py       # lov-remix-inject.py
│   │   ├── full_automation.py    # lovable-full-automation.py
│   │   ├── session_revival.py    # revive_sessions_login.py
│   │   ├── session_refresh.py    # lov-session-refresh-totp.py
│   │   ├── enable_2fa.py         # lov-2fa-enable.py
│   │   └── invite_automation.py  # lovable-invite-automation.py
│   ├── railway/                  # Railway automation
│   │   ├── account_creation.py   # railway-HOLY-zenrows.py
│   │   ├── verify_health.py      # railway_verify.py
│   │   └── api_client.py         # railway-API-WORKING.py
│   ├── farming/                  # Account farming scripts
│   │   ├── farm_single.py        # farm_one.py
│   │   ├── farm_zenrows_batch.py # farm_zenrows_10.py
│   │   ├── farm_zenrows_loop.py  # farm_zenrows_loop.py
│   │   └── zenrows_kernel.py     # zenrows-kernel-final.py
│   ├── onkernel/                 # OnKernel specific
│   │   ├── account_creation.py   # onk-api.py
│   │   └── org_reset.py          # onk-org-reset.py
│   ├── utils/                    # Utilities
│   │   ├── mail_providers.py     # mail_providers.py
│   │   ├── session_loader.py     # load_session.py
│   │   ├── check_dashboard.py    # check_sessions_dashboard.py
│   │   ├── build_cells.py        # build_cells.py
│   │   ├── build_services.py     # build_services.py
│   │   └── zenrows_balance.py    # zenrows_balance.py
│   └── __init__.py
├── archive/                      # OLD - Deprecated/superseded scripts
│   ├── lovable_old/              # Old Lovable scripts
│   ├── railway_old/              # Old Railway scripts
│   ├── browser_tests/            # Browser testing scripts
│   └── experimental/             # Experimental versions
├── tests/                        # Testing scripts
│   ├── test_turnstile.py
│   └── test_railway_flow.py
├── finals/                       # KEEP - Data and working scripts
│   ├── core/                     # Will be migrated to src/
│   └── *.json                    # Keep all JSON data files
├── scripts/                      # Will be reorganized
├── docs/                         # Documentation
└── sessions/                     # Keep as-is
```

## Migration Actions

### MOVE to src/lovable/
- finals/core/lov-api-effective.py → account_creation.py
- finals/core/lov-remix-inject.py → remix_inject.py
- finals/core/lovable-full-automation.py → full_automation.py
- scripts/revive_sessions_login.py → session_revival.py
- finals/core/lov-session-refresh-totp.py → session_refresh.py
- finals/core/lov-2fa-enable.py → enable_2fa.py
- finals/core/lovable-invite-automation.py → invite_automation.py

### MOVE to src/railway/
- railway-docker/railway-HOLY-zenrows.py → account_creation.py
- scripts/railway_verify.py → verify_health.py
- scripts/railway-API-WORKING.py → api_client.py

### MOVE to src/farming/
- finals/core/farm_one.py
- finals/core/farm_zenrows_10.py
- finals/core/farm_zenrows_loop.py
- finals/core/zenrows-kernel-final.py → zenrows_kernel.py

### MOVE to src/onkernel/
- finals/core/onk-api.py → account_creation.py
- finals/core/onk-org-reset.py → org_reset.py

### MOVE to src/utils/
- finals/core/mail_providers.py
- scripts/load_session.py → session_loader.py
- scripts/check_sessions_dashboard.py → check_dashboard.py
- scripts/build_cells.py
- scripts/build_services.py
- scripts/zenrows_balance.py

### MOVE to archive/lovable_old/
- finals/core/lov-api.py
- finals/core/lov-api-zenrows.py
- finals/core/lov-back.py
- finals/core/lov-final-working.py
- scripts/lov-f1.py
- scripts/lov-test.py
- scripts/lov-parallel.py
- scripts/lov3F.py
- scripts/lov3F_api_only.py

### MOVE to archive/railway_old/
- scripts/railway-login.py
- scripts/railway-login-with-mega*.py (all variants)
- scripts/railway-script.py
- scripts/railway-script2.py
- scripts/railway-mailtm*.py
- scripts/railway-turnstile-fast-poll.py

### MOVE to archive/browser_tests/
- scripts/browser-adblock-working.py
- scripts/browser-with-extension.py
- scripts/adguard-browser.py
- scripts/chrome-stable-adblock.py
- scripts/simple-browser-adblock.py
- scripts/ultimate-adblock.py
- scripts/open-warp-browser.py
- scripts/test-warp-browser.py

### MOVE to tests/
- finals/core/test_turnstile_click.py
- scripts/test-railway-flow.py

### DELETE (Old Railway deployment copies)
- scripts/railways/session-1/* (all subdirectories)

