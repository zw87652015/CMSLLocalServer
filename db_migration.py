#!/usr/bin/env python3
"""
Database migration script
"""

import os
import sqlite3
from pathlib import Path


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def migrate_database():
    """Apply all pending schema migrations"""
    db_path = Path(__file__).parent / 'database.db'

    if not db_path.exists():
        print("Database file not found. No migration needed.")
        return

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Migration 1: add comsol_version to tasks
        if not _column_exists(cursor, 'tasks', 'comsol_version'):
            cursor.execute("ALTER TABLE tasks ADD COLUMN comsol_version VARCHAR(10) DEFAULT '6.3'")
            cursor.execute("UPDATE tasks SET comsol_version = '6.3' WHERE comsol_version IS NULL")
            print("Added 'comsol_version' column to tasks table")
        else:
            print("'comsol_version' already exists, skipping")

        # Migration 2: add must_change_password to users
        if not _column_exists(cursor, 'users', 'must_change_password'):
            cursor.execute("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0")
            print("Added 'must_change_password' column to users table")
        else:
            print("'must_change_password' already exists, skipping")

        # Migration 3: rename user_<username> folders to user_<id>
        base = Path(__file__).parent
        cursor.execute("SELECT id, username FROM users")
        users = cursor.fetchall()
        for user_id, username in users:
            for sub in ('uploads', 'results', 'logs'):
                old_folder = base / sub / f"user_{username}"
                new_folder = base / sub / f"user_{user_id}"
                if old_folder.exists() and not new_folder.exists():
                    os.rename(old_folder, new_folder)
                    print(f"Renamed {old_folder} -> {new_folder}")

        # Migration 4: create server_config table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='server_config'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE server_config (
                    key   VARCHAR(64) PRIMARY KEY NOT NULL,
                    value TEXT NOT NULL
                )
            """)
            print("Created 'server_config' table")
        else:
            print("'server_config' already exists, skipping")

        # Migration 5: create nodes table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE nodes (
                    id                   VARCHAR(36)  PRIMARY KEY NOT NULL,
                    hostname             VARCHAR(255) NOT NULL,
                    ip_address           VARCHAR(45)  NOT NULL,
                    auth_token           VARCHAR(64)  NOT NULL UNIQUE,
                    comsol_versions_json TEXT         NOT NULL DEFAULT '[]',
                    cpu_cores            INTEGER      NOT NULL DEFAULT 1,
                    status               VARCHAR(20)  NOT NULL DEFAULT 'online',
                    current_task_id      VARCHAR(36),
                    registered_at        DATETIME,
                    last_seen            DATETIME
                )
            """)
            print("Created 'nodes' table")
        else:
            print("'nodes' already exists, skipping")

        # Migration 6: add assigned_node_id to tasks
        if not _column_exists(cursor, 'tasks', 'assigned_node_id'):
            cursor.execute("ALTER TABLE tasks ADD COLUMN assigned_node_id VARCHAR(36) REFERENCES nodes(id)")
            print("Added 'assigned_node_id' column to tasks table")
        else:
            print("'assigned_node_id' already exists, skipping")

        conn.commit()
        print("Migration complete.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
