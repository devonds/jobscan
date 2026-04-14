#!/bin/bash
# setup_cron.sh
# Sets up a nightly cron job to scrape Slack and sync to Google Sheets for Jobscan.

echo "Setting up nightly jobscan scraper..."

# Find the absolute path to jobscan script
# We assume it's installed via pip or uv and accessible in the current path.
JOBSCAN_CMD=$(command -v jobscan)

if [ -z "$JOBSCAN_CMD" ]; then
    echo "Error: 'jobscan' command not found in PATH."
    echo "Please ensure the jobscan tool is installed and activated."
    exit 1
fi

CRON_FILE="/tmp/jobscan_cron"
# Run every night at 2:00 AM
CRON_SCHEDULE="0 2 * * *"
CRON_COMMAND="$JOBSCAN_CMD slack scrape --all && $JOBSCAN_CMD slack sync"

# Save existing crontab to file, ignore error if no crontab exists
crontab -l > "$CRON_FILE" 2>/dev/null || true

# Remove any existing jobscan scrape/sync to avoid duplicates
grep -v "$JOBSCAN_CMD slack scrape --all" "$CRON_FILE" > "${CRON_FILE}.new"

# Add the new cron job
echo "$CRON_SCHEDULE $CRON_COMMAND" >> "${CRON_FILE}.new"

# Install the new crontab
crontab "${CRON_FILE}.new"

# Cleanup
rm "$CRON_FILE" "${CRON_FILE}.new"

echo "Success! The scraper will run every night at 2:00 AM."
echo "Current crontab:"
crontab -l
