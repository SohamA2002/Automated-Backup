#!/usr/bin/env python3
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
import logging
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configs from .env
PROJECT_NAME = os.getenv("PROJECT_NAME")
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL")
PROJECT_DIR = Path(os.getenv("PROJECT_DIR"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR")) / PROJECT_NAME
LOG_FILE = Path(os.getenv("LOG_FILE"))

RCLONE_REMOTE = os.getenv("RCLONE_REMOTE")
RCLONE_FOLDER = os.getenv("RCLONE_FOLDER")

RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", 7))
RETENTION_WEEKS = int(os.getenv("RETENTION_WEEKS", 4))
RETENTION_MONTHS = int(os.getenv("RETENTION_MONTHS", 3))

NOTIFY_URL = os.getenv("NOTIFY_URL")
ENABLE_NOTIFY = os.getenv("ENABLE_NOTIFY", "false").lower() == "true"

# Set up logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

def log(msg):
    print(msg)
    logging.info(msg)

def clone_repo():
    if not PROJECT_DIR.exists():
        log(f"Cloning repository from {GITHUB_REPO_URL}")
        subprocess.run(["git", "clone", GITHUB_REPO_URL, str(PROJECT_DIR)], check=True)

def create_zip():
    now = datetime.now()
    date_path = BACKUP_DIR / now.strftime("%Y/%m/%d")
    date_path.mkdir(parents=True, exist_ok=True)
    
    filename = f"{PROJECT_NAME.lower()}_{now.strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = date_path / filename

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(PROJECT_DIR):
            for file in files:
                full_path = Path(root) / file
                arcname = full_path.relative_to(PROJECT_DIR.parent)
                zipf.write(full_path, arcname)

    log(f"Created zip: {zip_path}")
    return zip_path

def upload_to_drive(zip_path):
    try:
        subprocess.run(["rclone", "copy", str(zip_path), f"{RCLONE_REMOTE}:{RCLONE_FOLDER}"], check=True)
        log(f"Uploaded to Google Drive folder: {RCLONE_FOLDER}")
    except subprocess.CalledProcessError:
        log("Upload to Google Drive failed.")

def send_notification(zip_path):
    if ENABLE_NOTIFY:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "project": PROJECT_NAME,
            "date": now,
            "status": "BackupSuccessful",
            "filename": zip_path.name
        }
        try:
            response = requests.post(NOTIFY_URL, json=payload)
            if response.status_code == 200:
                log("Notification sent to webhook")
            else:
                log(f"Webhook failed with status code {response.status_code}")
        except Exception as e:
            log(f"Notification error: {e}")

def delete_old_backups():
    deleted = {"daily": 0, "weekly": 0, "monthly": 0}
    now = datetime.now()

    for root, _, files in os.walk(BACKUP_DIR):
        for file in files:
            if not file.endswith(".zip"):
                continue
            file_path = Path(root) / file
            try:
                timestamp = datetime.strptime(file.split('_')[-1].replace('.zip', ''), '%Y%m%d_%H%M%S')
            except ValueError:
                continue

            age = (now - timestamp).days
            weekday = timestamp.weekday()
            day = timestamp.day

            if age > RETENTION_DAYS and weekday != 6 and day != 1:
                file_path.unlink()
                deleted["daily"] += 1
            elif weekday == 6 and age > RETENTION_WEEKS * 7:
                file_path.unlink()
                deleted["weekly"] += 1
            elif day == 1 and age > RETENTION_MONTHS * 30:
                file_path.unlink()
                deleted["monthly"] += 1

    log(f"Deleted {deleted['daily']} old daily backup(s)")
    log(f"Deleted {deleted['weekly']} old weekly backup(s)")
    log(f"Deleted {deleted['monthly']} old monthly backup(s)")

def main():
    log("Backup started")
    clone_repo()
    zip_path = create_zip()
    upload_to_drive(zip_path)
    delete_old_backups()
    send_notification(zip_path)
    log("Backup completed successfully")

if __name__ == "__main__":
    main()
