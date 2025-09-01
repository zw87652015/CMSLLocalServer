#!/usr/bin/env python3
"""
Database migration script to update User model for authentication and admin support
"""
import sqlite3
from pathlib import Path

def migrate_database():
    """Migrate database to new schema"""
    db_path = Path(__file__).parent / 'database.db'
    
    if not db_path.exists():
        print("No existing database found. New database will be created when app starts.")
        return
    
    print("Existing database found. Migrating schema...")
    
    # Connect directly to SQLite to modify schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check current table structure
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"Current columns: {columns}")
        
        # If we have the old browser_fingerprint schema, recreate the table
        if 'browser_fingerprint' in columns and 'username' not in columns:
            print("Converting from browser_fingerprint to username/password schema...")
            
            # Drop old table and recreate with new schema
            cursor.execute("DROP TABLE IF EXISTS users")
            cursor.execute("""
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_admin BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP,
                    last_seen TIMESTAMP
                )
            """)
            print("Created new users table with authentication schema")
            
        elif 'username' in columns:
            # Add missing columns to existing username/password schema
            if 'is_admin' not in columns:
                print("Adding is_admin column...")
                cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
            
            if 'is_active' not in columns:
                print("Adding is_active column...")
                cursor.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        
        # Update tasks table if needed
        cursor.execute("PRAGMA table_info(tasks)")
        task_columns = [column[1] for column in cursor.fetchall()]
        
        if 'tasks' not in [table[0] for table in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
            print("Creating tasks table...")
            cursor.execute("""
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    unique_filename TEXT UNIQUE NOT NULL,
                    file_size INTEGER,
                    status TEXT DEFAULT 'pending',
                    priority TEXT DEFAULT 'normal',
                    created_at TIMESTAMP,
                    queued_at TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    progress_percentage REAL DEFAULT 0.0,
                    current_step TEXT,
                    celery_task_id TEXT,
                    execution_time REAL,
                    queue_time REAL,
                    error_message TEXT,
                    error_log TEXT,
                    result_filename TEXT,
                    log_filename TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
        
        # Create system_stats table if needed
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_stats'")
        if not cursor.fetchone():
            print("Creating system_stats table...")
            cursor.execute("""
                CREATE TABLE system_stats (
                    id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP,
                    pending_tasks INTEGER DEFAULT 0,
                    running_tasks INTEGER DEFAULT 0,
                    completed_tasks_today INTEGER DEFAULT 0,
                    failed_tasks_today INTEGER DEFAULT 0,
                    cpu_usage REAL,
                    memory_usage REAL,
                    disk_usage REAL,
                    avg_queue_time REAL,
                    avg_execution_time REAL
                )
            """)
        
        conn.commit()
        print("Database migration completed successfully!")
        print("You can now start the application. Admin user will be created automatically.")
        
    except sqlite3.Error as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_database()
