"""Branch tree for the migration loop (plain sqlite3 on the head; modeled on
timing_opt/db.py). Each row = one variant of the workspace and its flow result."""
import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS branches (
    name          TEXT PRIMARY KEY,
    parent        TEXT,
    created       REAL,
    status        TEXT,     -- running | pass | fail | infra_error | error
    stage         TEXT,     -- syn | par
    rung          INTEGER,
    workspace_dir TEXT,
    obj_dir       TEXT,
    eval_json     TEXT,
    agent_log     TEXT
);
"""


class MigrationDB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def add(self, name, parent, stage, workspace_dir, obj_dir):
        self.conn.execute(
            "INSERT INTO branches (name,parent,created,status,stage,workspace_dir,obj_dir)"
            " VALUES (?,?,?,?,?,?,?)",
            (name, parent, time.time(), "running", stage, workspace_dir, obj_dir))
        self.conn.commit()

    def finish(self, name, status, rung, eval_result, agent_log=None):
        self.conn.execute(
            "UPDATE branches SET status=?, rung=?, eval_json=?, agent_log=? WHERE name=?",
            (status, rung, json.dumps(eval_result, default=str), agent_log, name))
        self.conn.commit()

    def get(self, name):
        r = self.conn.execute("SELECT * FROM branches WHERE name=?", (name,)).fetchone()
        return dict(r) if r else None

    def has_any(self):
        return self.conn.execute("SELECT 1 FROM branches LIMIT 1").fetchone() is not None

    def best(self):
        """Highest rung; ties -> most recent."""
        r = self.conn.execute(
            "SELECT * FROM branches WHERE rung IS NOT NULL AND status != 'infra_error'"
            " ORDER BY rung DESC, created DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def children(self, parent):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM branches WHERE parent=?", (parent,))]

    def all(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM branches ORDER BY created")]
