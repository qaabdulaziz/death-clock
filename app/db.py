"""SQLite persistence for Death Clock."""

from __future__ import annotations

import os
import sqlite3
import threading
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

_connection: sqlite3.Connection | None = None
_database_lock = threading.RLock()
F = TypeVar("F", bound=Callable[..., Any])

DEFAULT_SETTINGS: dict[str, Any] = {
    "date_of_birth": None,
    "life_expectancy_years": 80.0,
    "starting_balance": 0.0,
    "monthly_contribution": 0.0,
    "annual_return_rate": 7.0,
    "currency": "USD",
    "setup_complete": False,
}


def synchronized(function: F) -> F:
    """Serialize access to the process-local SQLite connection."""

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with _database_lock:
            return function(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def database_path() -> Path:
    """Return the configured database path, defaulting to the repository root."""

    return Path(os.environ.get("DEATHCLOCK_DB_PATH", "deathclock.db"))


@synchronized
def connection() -> sqlite3.Connection:
    """Return a process-local SQLite connection with named row access."""

    global _connection
    if _connection is None:
        _connection = sqlite3.connect(database_path(), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA foreign_keys = ON")
    return _connection


@synchronized
def reset_connection() -> None:
    """Close the current connection; primarily useful for isolated tests."""

    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


@synchronized
def initialize() -> None:
    """Create the schema and neutral settings row when absent."""

    conn = connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            date_of_birth DATE NULL,
            life_expectancy_years REAL NOT NULL DEFAULT 80.0,
            starting_balance REAL NOT NULL DEFAULT 0,
            monthly_contribution REAL NOT NULL DEFAULT 0,
            annual_return_rate REAL NOT NULL DEFAULT 7.0,
            currency TEXT NOT NULL DEFAULT 'USD',
            setup_complete BOOLEAN NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cost REAL NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO settings
            (id, date_of_birth, life_expectancy_years, starting_balance,
             monthly_contribution, annual_return_rate, currency, setup_complete)
        VALUES (1, NULL, 80.0, 0, 0, 7.0, 'USD', 0)
        """
    )
    conn.commit()


@synchronized
def get_settings() -> dict[str, Any]:
    row = connection().execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if row is None:
        initialize()
        row = connection().execute("SELECT * FROM settings WHERE id = 1").fetchone()
    result = dict(row)
    result["setup_complete"] = bool(result["setup_complete"])
    return result


@synchronized
def update_settings(values: dict[str, Any]) -> dict[str, Any]:
    if not values:
        return get_settings()
    allowed_columns = {
        "date_of_birth",
        "life_expectancy_years",
        "starting_balance",
        "monthly_contribution",
        "annual_return_rate",
        "currency",
        "setup_complete",
    }
    if not set(values).issubset(allowed_columns):
        raise ValueError("Unsupported settings field")
    columns = ", ".join(name + " = ?" for name in values)
    params = [value.isoformat() if hasattr(value, "isoformat") else value for value in values.values()]
    connection().execute("UPDATE settings SET " + columns + " WHERE id = 1", params)
    connection().commit()
    return get_settings()


@synchronized
def list_projects() -> list[dict[str, Any]]:
    rows = connection().execute("SELECT * FROM projects ORDER BY created_at, id").fetchall()
    return [dict(row) for row in rows]


@synchronized
def create_project(name: str, cost: float) -> dict[str, Any]:
    cursor = connection().execute("INSERT INTO projects (name, cost) VALUES (?, ?)", (name, cost))
    connection().commit()
    return get_project(cursor.lastrowid)


@synchronized
def get_project(project_id: int) -> dict[str, Any] | None:
    row = connection().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


@synchronized
def update_project(project_id: int, name: str, cost: float) -> dict[str, Any] | None:
    cursor = connection().execute(
        "UPDATE projects SET name = ?, cost = ? WHERE id = ?", (name, cost, project_id)
    )
    connection().commit()
    return get_project(project_id) if cursor.rowcount else None


@synchronized
def delete_project(project_id: int) -> bool:
    cursor = connection().execute("DELETE FROM projects WHERE id = ?", (project_id,))
    connection().commit()
    return bool(cursor.rowcount)


@synchronized
def reset_all() -> dict[str, Any]:
    conn = connection()
    with conn:
        conn.execute("DELETE FROM projects")
        conn.execute(
            """
            UPDATE settings SET date_of_birth = NULL, life_expectancy_years = 80.0,
                starting_balance = 0, monthly_contribution = 0,
                annual_return_rate = 7.0, currency = 'USD', setup_complete = 0
            WHERE id = 1
            """
        )
    return get_settings()
