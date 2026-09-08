import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUP_DIR = os.path.join(BASE_DIR, "backup")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")

NOTES_FILE = os.path.join(DATA_DIR, "notes.json")
RESOURCES_FILE = os.path.join(DATA_DIR, "resources.json")

NOTES_BACKUP_FILE = os.path.join(BACKUP_DIR, "notes_backup.json")
RESOURCES_BACKUP_FILE = os.path.join(BACKUP_DIR, "resources_backup.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)