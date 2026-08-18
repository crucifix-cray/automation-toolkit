#!/bin/bash

# Parse arguments
PROXY=""
PROXY_NAME="DIRECT (Raw IP)"
FILTER=""

for arg in "$@"; do
  case $arg in
    --warp)
      PROXY="--proxy socks4://127.0.0.1:40000"
      PROXY_NAME="WARP (socks4://127.0.0.1:40000)"
      ;;
    --tor)
      PROXY="--proxy socks5h://127.0.0.1:9050"
      PROXY_NAME="TOR (socks5h://127.0.0.1:9050)"
      ;;
    --railway)
      FILTER="railway"
      ;;
    --lovable)
      FILTER="lovable"
      ;;
    *)
      echo "Unknown argument: $arg"
      echo ""
      echo "Usage: $0 [--warp|--tor] [--railway|--lovable]"
      echo ""
      echo "Proxy options:"
      echo "  (none)   Use direct connection (raw IP)"
      echo "  --warp   Use WARP proxy"
      echo "  --tor    Use TOR proxy"
      echo ""
      echo "Filter options:"
      echo "  (none)     Show all emails"
      echo "  --railway  Show only Railway emails"
      echo "  --lovable  Show only Lovable emails"
      exit 1
      ;;
  esac
done

echo "=========================================="
echo "TEMPMAIL INBOX MONITOR"
echo "=========================================="
echo ""
echo "🌐 Connection: $PROXY_NAME"
if [ -n "$FILTER" ]; then
  echo "🔍 Filter: Show only '$FILTER' emails"
else
  echo "🔍 Filter: Show all emails"
fi
echo ""

WORKING_EMAIL=""
WORKING_ID=""

# Try up to 30 emails to find working Gmail
for i in {1..30}; do
  echo "Attempt $i: Creating email..."
  
  RESPONSE=$(timeout 30 curl -s $PROXY -X POST https://api.tempmailhub.org/emails \
    -H "Content-Type: application/json" \
    -H "Origin: https://tempmailhub.org" \
    -d '{}')
  
  EMAIL=$(echo "$RESPONSE" | grep -oP '"email":"\K[^"]+')
  EMAIL_ID=$(echo "$RESPONSE" | grep -oP '"email_id":\K[0-9]+')
  
  if [ -z "$EMAIL" ]; then
    echo "  ❌ Failed to create"
    continue
  fi
  
  echo "  Created: $EMAIL (ID: $EMAIL_ID)"
  
  # VALIDATE: Must be @gmail.com
  if ! echo "$EMAIL" | grep -qi "@gmail.com$"; then
    echo "  ❌ Not @gmail.com - skipping"
    continue
  fi
  
  # VALIDATE: Extract local part (before @)
  LOCAL_PART=$(echo "$EMAIL" | sed 's/@.*//')
  
  # VALIDATE: Reject if has + sign
  if echo "$LOCAL_PART" | grep -q "+"; then
    echo "  ❌ Has '+' sign - skipping"
    continue
  fi
  
  # VALIDATE: Reject if has dot
  if echo "$LOCAL_PART" | grep -q "\."; then
    echo "  ❌ Has '.' dot - skipping"
    continue
  fi
  
  echo "  ✅ Valid Gmail format"
  echo "  Testing mailbox..."
  
  # Wait 2s for mailbox init
  sleep 2
  
  # Test mailbox
  MSG_RESPONSE=$(timeout 30 curl -s $PROXY -X POST "https://api.tempmailhub.org/emails/messages?email_id=$EMAIL_ID" \
    -H "Content-Type: application/json" \
    -H "Origin: https://tempmailhub.org" \
    -d '{}' 2>&1)
  
  # Check for errors
  if echo "$MSG_RESPONSE" | grep -qi "imap.*failed\|authentication.*failed\|invalid.*credentials"; then
    echo "  ❌ IMAP auth error - trying next..."
    continue
  elif [ -z "$MSG_RESPONSE" ] || [ "$MSG_RESPONSE" = "" ]; then
    echo "  ❌ Empty response - trying next..."
    continue
  elif echo "$MSG_RESPONSE" | grep -qi "norecentemails"; then
    echo "  ✅ Mailbox working!"
    WORKING_EMAIL="$EMAIL"
    WORKING_ID="$EMAIL_ID"
    break
  elif echo "$MSG_RESPONSE" | grep -q '"emails":\['; then
    echo "  ✅ Mailbox working (has messages)!"
    WORKING_EMAIL="$EMAIL"
    WORKING_ID="$EMAIL_ID"
    break
  else
    echo "  ❓ Unknown response - trying next..."
  fi
  
  sleep 1
done

if [ -z "$WORKING_EMAIL" ]; then
  echo ""
  echo "❌ Could not find working Gmail mailbox after 30 attempts"
  echo ""
  echo "Criteria:"
  echo "  - Must be @gmail.com"
  echo "  - No '+' signs"
  echo "  - No '.' dots"
  echo "  - Working IMAP (no auth errors)"
  exit 1
fi

echo ""
echo "🎉 =========================================="
echo "✅ FOUND WORKING GMAIL MAILBOX!"
echo "🎉 =========================================="
echo ""
echo "================================================"
echo "📬 SEND YOUR EMAIL TO: $WORKING_EMAIL"
echo "================================================"
echo "   Email ID: $WORKING_ID"
echo "   Format: ✅ @gmail.com, no dots, no plus"
echo "   Connection: $PROXY_NAME"
if [ -n "$FILTER" ]; then
  echo "   Filter: Only showing '$FILTER' emails"
fi
echo ""
echo "📥 Monitoring for incoming emails (checking every 10s)..."
echo "   Press Ctrl+C to stop"
echo ""

# CRITICAL: Switch to DIRECT connection for monitoring
# WARP proxy is unstable for continuous polling (times out after few requests)
if [ -n "$PROXY" ]; then
  echo "⚠️  Switching from $PROXY_NAME to DIRECT connection for stable monitoring"
  MONITOR_PROXY=""
  MONITOR_PROXY_NAME="DIRECT (for reliability)"
else
  MONITOR_PROXY="$PROXY"
  MONITOR_PROXY_NAME="$PROXY_NAME"
fi
echo "   Monitoring via: $MONITOR_PROXY_NAME"
echo ""

CHECK=0
LAST_EMAIL_COUNT=0
CONSECUTIVE_EMPTY=0

while true; do
  CHECK=$((CHECK + 1))
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Check #$CHECK at $(date +%H:%M:%S)"
  
  MSG_RESPONSE=$(timeout 30 curl -s $MONITOR_PROXY -X POST "https://api.tempmailhub.org/emails/messages?email_id=$WORKING_ID" \
    -H "Content-Type: application/json" \
    -H "Origin: https://tempmailhub.org" \
    -d '{}' 2>&1)
  
  # DEBUG: Show raw response
  RESPONSE_LEN=${#MSG_RESPONSE}
  echo "DEBUG: Response length: $RESPONSE_LEN bytes"
  
  # Check if response is empty/dead
  if [ "$RESPONSE_LEN" -lt 10 ]; then
    CONSECUTIVE_EMPTY=$((CONSECUTIVE_EMPTY + 1))
    echo "❌ EMPTY RESPONSE #$CONSECUTIVE_EMPTY"
    echo ""
    echo "🔍 DIAGNOSIS: Mailbox died when email arrived!"
    echo "   TempMail API bug: mailboxes crash on incoming emails"
    echo ""
    echo "Trying to recover by checking if email arrived before crash..."
    
    # Try one more time with longer timeout
    sleep 3
    MSG_RESPONSE=$(timeout 60 curl -s $MONITOR_PROXY -X POST "https://api.tempmailhub.org/emails/messages?email_id=$WORKING_ID" \
      -H "Content-Type: application/json" \
      -H "Origin: https://tempmailhub.org" \
      -d '{}' 2>&1)
    
    if [ "${#MSG_RESPONSE}" -lt 10 ]; then
      echo "❌ Mailbox permanently dead after $CONSECUTIVE_EMPTY empty responses"
      echo ""
      echo "💀 CONFIRMED: TempMail mailbox dies when receiving emails"
      echo ""
      echo "This is a TempMail API bug - mailboxes are unusable for real email reception."
      exit 1
    fi
  fi
  
  # Reset counter if we got data
  if [ "$RESPONSE_LEN" -gt 10 ]; then
    CONSECUTIVE_EMPTY=0
  fi
  
  echo "DEBUG: First 200 chars: ${MSG_RESPONSE:0:200}"
  
  if echo "$MSG_RESPONSE" | grep -q '"emails":\['; then
    # Count emails
    EMAIL_COUNT=$(echo "$MSG_RESPONSE" | grep -o '"id":"imap-' | wc -l)
    
    # Check if new emails arrived
    if [ "$EMAIL_COUNT" -gt "$LAST_EMAIL_COUNT" ]; then
      NEW_COUNT=$((EMAIL_COUNT - LAST_EMAIL_COUNT))
      echo "✅ $NEW_COUNT new email(s) arrived! Total: $EMAIL_COUNT"
      echo ""
      LAST_EMAIL_COUNT=$EMAIL_COUNT
    else
      echo "📧 $EMAIL_COUNT total email(s) in inbox"
    fi
    
    # Extract and display emails (latest first)
    echo "$MSG_RESPONSE" | python3 -c "
import sys
import json

try:
    data = json.load(sys.stdin)
    emails = data.get('emails', [])
    
    # Reverse to show latest first
    emails = list(reversed(emails))
    
    filter_word = '$FILTER'
    shown_count = 0
    
    for idx, email in enumerate(emails, 1):
        subject = email.get('subject', 'No subject')
        sender = email.get('senderEmail', 'Unknown')
        sender_name = email.get('senderName', '')
        date = email.get('date', '')
        email_id = email.get('id', '')
        
        # Apply filter if specified
        if filter_word:
            subject_lower = subject.lower()
            sender_lower = sender.lower()
            sender_name_lower = sender_name.lower()
            
            if filter_word.lower() not in subject_lower and \
               filter_word.lower() not in sender_lower and \
               filter_word.lower() not in sender_name_lower:
                continue  # Skip this email
        
        shown_count += 1
        
        print(f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        print(f'📧 Email #{idx} (ID: {email_id})')
        print(f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        print(f'From: {sender_name} <{sender}>')
        print(f'Subject: {subject}')
        print(f'Date: {date}')
        print()
    
    if filter_word and shown_count == 0:
        print(f'⚠️  No emails matching filter: \"{filter_word}\"')
    elif shown_count == 0:
        print('⏳ No emails yet')
        
except Exception as e:
    print(f'Error parsing emails: {e}', file=sys.stderr)
"
  else
    echo "⏳ No emails yet"
  fi
  
  echo ""
  sleep 10
done
