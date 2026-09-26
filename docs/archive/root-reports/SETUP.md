# Automation Toolkit - Setup Guide

Complete setup instructions for the automation-toolkit project.

---

## 📋 Prerequisites

- **Python**: 3.10 or higher
- **Operating System**: Linux (primary), macOS (should work), Windows (untested, use WSL)
- **Git**: For cloning and version control
- **Node.js**: 16+ (for Railway CLI)

---

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone <repository-url>
cd automation-toolkit
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows
```

### 3. Install Python Dependencies

```bash
# Install main dependencies
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt
```

### 4. Install Browser Drivers

```bash
# Install Playwright browsers
playwright install chromium firefox

# Install Patchright browsers (for anti-detection)
patchright install chromium

# Install system dependencies (Linux only)
playwright install-deps
```

### 5. Install External Tools

#### Railway CLI
```bash
# macOS
brew install railway

# Linux
curl -fsSL https://railway.app/install.sh | sh

# Verify
railway --version
```

#### rclone (for Mega cloud storage)
```bash
# macOS
brew install rclone

# Linux
sudo apt-get install rclone

# Verify
rclone version
```

#### Tor (optional, for some scripts)
```bash
# Linux
sudo apt-get install tor

# macOS
brew install tor
```

### 6. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# API Keys
KERNEL_API_KEY=your_onkernel_api_key_here
ZENROWS_API_KEY=your_zenrows_api_key_here

# GitHub (optional)
GH_TOKEN=your_github_token_here

# Railway (set via railway login)
# No need to add here

# Proxy settings (optional)
# HTTP_PROXY=http://proxy:port
# HTTPS_PROXY=http://proxy:port
```

### 7. Authenticate Services

```bash
# Railway CLI
railway login

# Verify
railway whoami
```

### 8. Verify Installation

```bash
# Test Python installation
python3 --version

# Test package imports
python3 -c "import playwright; print('Playwright OK')"
python3 -c "import patchright; print('Patchright OK')"
python3 -c "import pyotp; print('PyOTP OK')"

# Test Railway CLI
railway whoami

# Test rclone
rclone version
```

---

## 📁 Repository Structure

After setup, your repository should look like this:

```
automation-toolkit/
├── src/                  # Active working scripts
│   ├── lovable/          # Lovable.dev automation
│   ├── railway/          # Railway.com automation
│   ├── farming/          # Account farming scripts
│   ├── onkernel/         # OnKernel operations
│   └── utils/            # Shared utilities
├── sessions/             # Railway + Lovable sessions (1-51)
├── finals/               # Data files and original scripts
├── archive/              # Deprecated scripts
├── tests/                # Test scripts
├── docs/                 # Documentation
├── requirements.txt      # Python dependencies
└── .env                  # Environment variables (create this)
```

---

## 🔧 Configuration

### Session Directories

Sessions are stored in `sessions/session-1` through `sessions/session-51`. Each contains:
- Railway configuration (`railway_cli_config.json`)
- SSH keys (`.ssh/`)
- Email address (`email.txt`)
- Lovable tokens (some have `config.json`)

### Data Files

Key data files in the root:
- `session_mapping.json` - Maps sessions to Railway and Lovable accounts
- `cells.json` - Railway cell configurations
- `finals/railway_sessions.json` - Current Railway session data
- `finals/lovable_accounts_master.json` - All Lovable accounts (69)

### Mega Cloud Storage

If using Mega for data storage:

```bash
# Configure rclone for Mega
rclone config

# Test connection
rclone lsd remote-name:

# Sync data
rclone sync remote-name:/path/to/data ./local/path
```

---

## ✅ Verification Checklist

- [ ] Python 3.10+ installed
- [ ] Virtual environment created and activated
- [ ] All Python packages installed (`pip list`)
- [ ] Playwright browsers installed (`playwright install`)
- [ ] Railway CLI installed and authenticated
- [ ] rclone installed (if using Mega)
- [ ] Environment variables configured (`.env`)
- [ ] Can import all required packages in Python
- [ ] Sessions directory exists with 51 session folders
- [ ] Data files exist (`session_mapping.json`, `cells.json`, etc.)

---

## 🎯 Quick Test Runs

### Test Lovable Session Revival

```bash
cd src/lovable/
python3 session_revival.py --pth 1  # Test session-1 only
```

### Test Railway Health Check

```bash
cd src/railway/
python3 verify_health.py --pth 1  # Test session-1 only
```

### Test Session Loader

```bash
cd src/utils/
python3 session_loader.py --list  # List all sessions
python3 session_loader.py 1       # Load session-1
```

### Test ZenRows Balance

```bash
cd src/utils/
python3 zenrows_balance.py
```

---

## 🐛 Troubleshooting

### Issue: "Module not found" errors

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall requirements
pip install -r requirements.txt --force-reinstall
```

### Issue: Playwright browser not found

```bash
# Reinstall browsers
playwright install chromium firefox
playwright install-deps  # Linux only
```

### Issue: Railway authentication fails

```bash
# Re-authenticate
railway logout
railway login
railway whoami
```

### Issue: Import errors with playwright variants

The project uses three Playwright forks: `playwright`, `patchright`, and `invisible-playwright`. They may conflict. Solutions:

1. **Use separate virtual environments**:
```bash
# Create environments for different tools
python3 -m venv venv-lovable      # For invisible-playwright
python3 -m venv venv-railway      # For patchright
python3 -m venv venv-farming      # For playwright
```

2. **Install only what you need**:
```bash
# If only using Lovable scripts
pip install invisible-playwright pyotp

# If only using Railway scripts
pip install patchright httpx
```

### Issue: Permission denied on session directories

```bash
# Fix permissions
chmod -R 755 sessions/
chmod 600 sessions/session-*/railway_cli_config.json
chmod 600 sessions/session-*/.ssh/*
```

### Issue: Scripts fail with path errors

Many scripts use absolute paths. Update them:
```python
# Old
SESSIONS_DIR = Path("/home/alan/Documents/automation-toolkit/scripts/sessions")

# New
SESSIONS_DIR = Path(__file__).parent.parent.parent / "sessions"
```

---

## 📚 Next Steps

After setup:

1. **Read Documentation**:
   - `src/README.md` - Active scripts overview
   - `SCRIPT_INVENTORY.md` - Complete script catalog
   - `DATA_SOURCES.md` - Data organization
   - `CONSOLIDATION_REPORT.md` - Account consolidation

2. **Review Session Mapping**:
   - Open `session_mapping.json`
   - Understand Railway → Lovable mappings

3. **Test Basic Workflows**:
   - Run session revival for one session
   - Verify Railway health for one session
   - Load a session in browser

4. **Plan Your Automation**:
   - Determine which sessions need Lovable accounts
   - Assign Lovable accounts to sessions
   - Test full automation workflow

---

## 🔐 Security Notes

- **Never commit** `.env` file to git
- **Never commit** session cookies or tokens
- **Keep secrets** in environment variables or external vaults
- **Rotate credentials** regularly
- **Use .gitignore** for sensitive files

### Recommended .gitignore additions

```
# Secrets
.env
*.key
*.pem

# Session data
sessions/*/cookies.json
sessions/*/config.json

# Credentials
*_credentials.json
*_tokens.json

# Logs
*.log
runs.log
```

---

## 💡 Tips

1. **Use virtual environments** - Avoid package conflicts
2. **Update regularly** - `pip install --upgrade -r requirements.txt`
3. **Test in isolation** - Test one session before scaling
4. **Monitor resources** - Browser automation is memory-intensive
5. **Read script headers** - Each script has usage docs at the top

---

## 📞 Support

- Documentation: See markdown files in repo root
- Issues: Review `SCRIPT_INVENTORY.md` for known issues
- Updates: Check git log for recent changes

---

## 📊 System Requirements

### Minimum

- CPU: 2 cores
- RAM: 4 GB
- Disk: 10 GB free
- Network: Stable broadband

### Recommended

- CPU: 4+ cores
- RAM: 8+ GB
- Disk: 20+ GB SSD
- Network: 10+ Mbps

### For Heavy Automation (51 sessions)

- CPU: 8+ cores
- RAM: 16+ GB
- Disk: 50+ GB SSD
- Network: 50+ Mbps

