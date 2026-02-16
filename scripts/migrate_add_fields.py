"""One-time migration to add new fields to existing database."""
import sqlite3
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/jobs.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Add priority column to job table
try:
    cursor.execute("ALTER TABLE job ADD COLUMN priority INTEGER DEFAULT 5")
    print("Added 'priority' column to job table")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("'priority' column already exists")
    else:
        raise

# Add cost_estimate column to stageresult table
try:
    cursor.execute("ALTER TABLE stageresult ADD COLUMN cost_estimate REAL DEFAULT 0.0")
    print("Added 'cost_estimate' column to stageresult table")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("'cost_estimate' column already exists")
    else:
        raise

conn.commit()
conn.close()
print("Migration complete")
