# Kill Switch Instructions

## Stop All Account Creation

To stop all running instances from creating more accounts:

```bash
# Create stop signal file
echo "STOP" | rclone rcat mega:stop.txt
```

All running containers will detect this file and gracefully shut down within ~10 seconds.

## Resume Account Creation

To resume (remove stop signal):

```bash
# Remove stop file
rclone delete mega:stop.txt
```

## Check Current Status

```bash
# Check account count
rclone cat mega:railway_sessions/counter.txt

# Check if stop signal is active
rclone ls mega:stop.txt
# (If file exists, stop signal is active)

# List all sessions
rclone ls mega:railway_sessions
```

## Manual Counter Reset

```bash
# Reset counter to 0
echo "0" | rclone rcat mega:railway_sessions/counter.txt

# Set counter to specific number
echo "100" | rclone rcat mega:railway_sessions/counter.txt
```

## Emergency Stop (Force)

If kill switch doesn't work:

1. Delete all Railway projects manually via web UI
2. Remove all containers
3. Reset counter in Mega

## Monitoring

```bash
# Watch counter in real-time
watch -n 5 'rclone cat mega:railway_sessions/counter.txt'

# Count sessions in Mega
rclone ls mega:railway_sessions | grep "session-" | wc -l
```
