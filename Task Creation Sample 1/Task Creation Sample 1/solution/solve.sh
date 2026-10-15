#!/bin/bash
cd /app

# Execute a quick Python inline snippet to natively build the database and insert data
python -c "
import sqlite3
conn = sqlite3.connect('UGC_VIDEOS.db')
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS video_files (video_id TEXT, file_name TEXT, duration TEXT, fps TEXT, height INTEGER, width INTEGER)')
c.execute('INSERT INTO video_files VALUES (?, ?, ?, ?, ?, ?)', ('vid_001', 'on the sky', '30 second', '60 fps', 760, 1200))
conn.commit()
conn.close()
"