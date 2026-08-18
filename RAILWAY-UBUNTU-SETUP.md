# Railway Ubuntu Terminal Setup Guide

## 🚀 Quick Deploy

**1. Delete old Railway service:**
   - Open: https://railway.com/project/9cdaada9-cb0f-41cb-9a61-7a61310e8421
   - Delete service: `farm-1786563480`

**2. Deploy Ubuntu 24.04 LTS template:**
   - Click: https://railway.com/deploy/ubuntu-2404-lts-web-terminal--ubuntu-2404-lts-web-terminal
   - Select project: `farm-1786563480`
   - Set environment variables:
     - `USERNAME`: railway
     - `PASSWORD`: (set strong password)
   - Deploy!

**3. Wait for deployment (~2-3 minutes)**

**4. Get your terminal URL:**
   - Railway will provide a public URL like: `https://xxxxx.railway.app`

---

## 🛠️ Install All Tools (Run in Terminal)

**Copy & paste into Railway web terminal:**

```bash
# Download setup script
wget https://raw.githubusercontent.com/cold-pressed-hoodie/automation-toolkit/main/railway-ubuntu-setup.sh -O /tmp/setup.sh

# Run setup
bash /tmp/setup.sh
```

**What gets installed:**
- ✅ Python 3.11 + pip
- ✅ Playwright + Chromium + all dependencies
- ✅ WireGuard + wgcf (Cloudflare WARP)
- ✅ rclone (Mega cloud sync)
- ✅ Railway CLI
- ✅ All system libraries needed for headless Chrome

**Setup takes ~5-10 minutes**

---

## 🧪 Test Browser

**After setup completes, test Chromium:**

```bash
# Download test script
wget https://raw.githubusercontent.com/cold-pressed-hoodie/automation-toolkit/main/railway-ubuntu-test-browser.py -O /data/test-browser.py

# Run test
python3 /data/test-browser.py
```

**Expected output:**
```
🎭 TESTING PLAYWRIGHT CHROMIUM IN RAILWAY
📦 Launching Chromium (headless)...
✅ Browser launched!
📄 Creating new page...
✅ Page created!
🌐 Navigating to Railway.com...
✅ Navigation successful!
📝 Page title: Railway
✅ Browser closed!
🎉 ALL TESTS PASSED!
```

---

## 📦 Configure Services

### **rclone (Mega sync)**

```bash
rclone config
# n) New remote
# name> mega
# Storage> mega
# user> your-mega-email
# pass> your-mega-password
# y) Yes this is OK
# q) Quit config
```

### **Copy Railway credentials**

```bash
# Create session directory
mkdir -p /data/railways/session-1

# Copy from local (you'll need to upload these via Railway terminal)
# Files needed:
# - /data/railways/session-1/.railway-token
# - /data/railways/session-1/config.json

# Verify
ls -la /data/railways/session-1/
```

### **Setup WARP**

```bash
cd /data

# Start WARP
wg-quick up ./wgcf-profile.conf

# Test
curl --socks4 127.0.0.1:40000 https://cloudflare.com/cdn-cgi/trace

# Should show warp=on
```

---

## 🚀 Run Automation Script

**Copy main script:**

```bash
wget https://raw.githubusercontent.com/cold-pressed-hoodie/automation-toolkit/main/railway-docker/railway-mailtm-full.py -O /data/scripts/railway-mailtm-full.py

chmod +x /data/scripts/railway-mailtm-full.py
```

**Test single account:**

```bash
cd /data/scripts
python3 railway-mailtm-full.py --warp
```

**Run continuous (farm mode):**

```bash
cd /data/scripts
python3 railway-mailtm-full.py --warp --continuous --max-accounts 8000
```

**Run with recursive deployment:**

```bash
cd /data/scripts
python3 railway-mailtm-full.py --warp --continuous --deploy-recursive
```

---

## 📊 Monitor

**Check counter:**
```bash
rclone cat mega:railway_sessions/counter.txt
```

**Check logs:**
```bash
tail -f /tmp/railway-automation.log
```

**Check created accounts:**
```bash
rclone ls mega:railway_sessions | grep session-
```

---

## 🎯 Important Notes

1. **Only `/data` persists** - put everything important there
2. **After redeploy** - rerun setup.sh (apt packages don't persist)
3. **Memory limit** - Railway Hobby plan has 8GB max per service
4. **Counter starts at 0** - first account increments to 1
5. **WARP proxy** - uses socks4://127.0.0.1:40000

---

## 🆘 Troubleshooting

**Browser won't start:**
```bash
# Reinstall Playwright
python3 -m patchright install chromium
python3 -m patchright install-deps
```

**WARP not working:**
```bash
# Restart WARP
wg-quick down ./wgcf-profile.conf
wg-quick up ./wgcf-profile.conf
```

**Memory issues:**
```bash
# Check usage
free -h
# If >90%, upgrade to Hobby plan
```

**Script hangs:**
```bash
# Kill processes
pkill -9 python3
pkill -9 chromium
```

---

## 📈 Upgrade to Hobby Plan

If you hit memory limits (1GB free tier):

1. Go to: https://railway.com/account/billing
2. Subscribe to Hobby plan: $5/month
3. Get 8GB RAM limit per service
4. Billing: $10/GB RAM per month, $20/vCPU per month

**Estimated cost for 1 automation instance:**
- RAM: ~2GB = $20/month
- CPU: ~0.5 vCPU = $10/month
- **Total: ~$30/month**

(Hobby plan $5 includes $5 credits)

---

## ✅ Success Criteria

- [ ] Ubuntu terminal accessible via browser
- [ ] All tools installed (setup.sh completes)
- [ ] Browser test passes (test-browser.py)
- [ ] rclone configured for Mega
- [ ] WARP connected
- [ ] Railway CLI authenticated
- [ ] Script creates first account (counter = 1)

**Then you're ready for the farm! 🚀**
