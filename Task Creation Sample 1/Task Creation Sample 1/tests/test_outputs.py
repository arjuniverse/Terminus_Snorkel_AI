import os
import sqlite3
import pytest

DB_PATH = "/app/UGC_VIDEOS.db"

def test_database_and_table_exist():
    """Verify that the agent correctly created the file and table structure."""
    assert os.path.exists(DB_PATH), "UGC_VIDEOS.db was not found in /app"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_files';")
    assert cursor.fetchone() is not None, "Table 'video_files' does not exist."
    conn.close()

def test_data_insertion():
    """Verify that the target test record was correctly committed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM video_files WHERE video_id = 'vid_001';")
    row = cursor.fetchone()
    
    assert row is not None, "Target record 'vid_001' was not found."
    # Validating the columns: video_id, file_name, duration, fps, height, width
    assert row[1] == "on the sky"
    assert row[2] == "30 second"
    assert row[3] == "60 fps"
    assert row[4] == 760
    assert row[5] == 1200
    conn.close()