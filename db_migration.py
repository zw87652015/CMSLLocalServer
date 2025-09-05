#!/usr/bin/env python3
"""
Database migration script to add comsol_version column to tasks table
"""

import sqlite3
import os
from pathlib import Path

def migrate_database():
    """Add comsol_version column to existing tasks table"""
    
    # Database path
    db_path = Path(__file__).parent / 'database.db'
    
    if not db_path.exists():
        print("Database file not found. No migration needed.")
        return
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'comsol_version' in columns:
            print("Column 'comsol_version' already exists. No migration needed.")
            return
        
        # Add the new column
        cursor.execute("ALTER TABLE tasks ADD COLUMN comsol_version VARCHAR(10) DEFAULT '6.3'")
        
        # Update existing tasks to have default version
        cursor.execute("UPDATE tasks SET comsol_version = '6.3' WHERE comsol_version IS NULL")
        
        # Commit changes
        conn.commit()
        print("✅ Successfully added 'comsol_version' column to tasks table")
        print("✅ Set default COMSOL version 6.3 for existing tasks")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        conn.rollback()
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
