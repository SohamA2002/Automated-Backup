# 🚀 Automated Backup and Rotation Script with Google Drive Integration

## 📃 Overview

This project provides a Python-based backup automation tool that:
- Backs up any project directory as a `.zip` file
- Organizes backups in timestamped folders (daily/weekly/monthly)
- Uploads them to Google Drive via `rclone`
- Rotates/deletes old backups based on retention policy
- Sends notifications via a webhook

---

## 📁 Project Structure

```bash
~/auto-backup-project/
├── backups/ # Local backups
├── logs/ # Log files
├── config/ # Reserved for advanced configs
├── backup.py # Main Python script
├── .env # Environment variables
├── venv/ # Python virtual environment
```

---

## 🛠️ Step-by-Step Setup Guide

### ✅ Step 1: Prepare the Environment

#### 1.1 Update System and Install Dependencies

```bash
sudo apt upgrade -y
sudo apt install python3 python3-pip unzip python3-venv zip curl git cron -y
```

#### 1.2 Create Project Directory Structure

```bash
mkdir -p ~/auto-backup-project/{backups,logs,config}
cd ~/auto-backup-project
touch backup.py .env README.md
python3 -m venv venv
source venv/bin/activate
pip install python-dotenv
```

```bash
1.3 Install rclone
```

```bash
curl https://rclone.org/install.sh | sudo bash
rclone version
```

---

### ☁️ Step 2: Google Drive Integration with rclone

#### 2.1 Configure Remote

```bash
rclone config
```

* Create new remote: `n`
* Name: `gdrive`
* Storage: `drive`
* Auto config: `n`
* Run this on your local PC:

```bash
rclone authorize "drive" "eyJzY29wZSI6ImRyaXZlIn0"
```

* Paste the access token on EC2.
* Choose `n` for team drive.

#### 2.2 Test Upload

```bash
echo "Hello from EC2" > test.txt
rclone copy test.txt gdrive:EC2Backups
```

---

### 📁 Step 3: .env Configuration File

Create `.env` file inside `~/auto-backup-project/`:

```dotenv
# Project Info
PROJECT_NAME=MyProject
GITHUB_REPO_URL=https://github.com/SohamA2002/Automated-Backup.git
PROJECT_DIR=/home/ubuntu/MyProject

# Backup
BACKUP_DIR=/home/ubuntu/auto-backup-project/backups

# Retention Policy
RETENTION_DAYS=7
RETENTION_WEEKS=4
RETENTION_MONTHS=3

# Google Drive
RCLONE_REMOTE=gdrive
RCLONE_FOLDER=EC2Backups

# Logging
LOG_FILE=/home/ubuntu/auto-backup-project/logs/backup.log

# Notification
NOTIFY_URL=https://webhook.site/your-custom-url
ENABLE_NOTIFY=true
```

---

### 🖊️ Step 4: Python Backup Script

Save the following as `backup.py` inside `~/auto-backup-project/`.

The script:

* Loads environment config.
* Clones GitHub repo if not already cloned.
* Zips the project.
* Uploads via rclone.
* Deletes old backups per retention rules.
* Logs actions.
* Sends webhook (if enabled).

```python
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
```

Run the script manually:

```bash
chmod +x backup.py
source venv/bin/activate
python3 backup.py
```

---

### ⏰ Step 5: Schedule with cron

To automate the script every day at 2:00 AM:

```bash
crontab -e
```

Add this line:

```cron
0 2 * * * /home/ubuntu/auto-backup-project/venv/bin/python3 /home/ubuntu/auto-backup-project/backup.py >> /home/ubuntu/auto-backup-project/logs/cron.log 2>&1
```

Verify with:

```bash
crontab -l
```

---

## 🔄 Retention Strategy

The script deletes old backups using:

* **Daily:** Keep last 7 days.
* **Weekly:** Keep backups from last 4 Sundays.
* **Monthly:** Keep backups from the 1st of each of the last 3 months.

These values are adjustable in `.env`.

---

## 📃 Log File Example (backup.log)

```
[2025-07-21 02:00:00] Backup started
[2025-07-21 02:00:01] Created zip: myproject_20250721_020000.zip
[2025-07-21 02:00:02] Uploaded to Google Drive folder: EC2Backups
[2025-07-21 02:00:03] Deleted 1 old daily backup(s)
[2025-07-21 02:00:04] Notification sent to webhook
[2025-07-21 02:00:04] Backup completed successfully
```

---

## 📧 Webhook Notification

Sample payload sent to `NOTIFY_URL`:

```json
{
  "project": "MyProject",
  "date": "2025-07-21 02:00:00",
  "status": "BackupSuccessful"
}
```

To disable webhook notification:

```dotenv
ENABLE_NOTIFY=false
```

---

## ⚠️ Security Considerations

* Use personal OAuth credentials when deploying in production.
* Store `.env` with proper permissions (`chmod 600 .env`).
* Make sure `rclone` token access is restricted.
* Avoid hardcoding secrets; use environment files.

---

## 👤 Author

**Srushti Deshmukh**
DevOps Projects Portfolio
GitHub: [Srushtideshmukh44](https://github.com/Srushtideshmukh44)

---

## 🗕️ Example Crontab Entry

```cron
0 2 * * * /home/ubuntu/auto-backup-project/venv/bin/python3 /home/ubuntu/auto-backup-project/backup.py >> /home/ubuntu/auto-backup-project/logs/cron.log 2>&1
```
