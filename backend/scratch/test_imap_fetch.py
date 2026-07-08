import sys
import os
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.db import get_email_config
from app.services.automation import fetch_unread_emails_sync

if __name__ == "__main__":
    print("--- Testing IMAP Config & Fetch ---")
    config = get_email_config()
    if not config:
        print("No active email configuration found in database.")
        sys.exit(0)

    print(f"Active email configuration: {config['email_address']} on {config['imap_server']}:{config['imap_port']}")

    try:
        print("Testing fetch_unread_emails_sync...")
        emails = fetch_unread_emails_sync()
        print(f"Successfully polled server. Found {len(emails)} unread emails with attachments.")
        for idx, email_item in enumerate(emails):
            print(f"[{idx+1}] From: {email_item['sender']} | Subject: {email_item['subject']} | Attachment: {email_item['filename']}")
    except Exception as e:
        print(f"Error testing fetch: {e}")
