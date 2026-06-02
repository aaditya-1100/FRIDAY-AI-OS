import sqlite3
import json
import os

DB_PATH = r"C:\FRIDAY\backend\data\routing_telemetry.db"

if not os.path.exists(DB_PATH):
    print("Database does not exist at:", DB_PATH)
    exit(0)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("--- TELEMETRY TABLES ---")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

print("\n--- ROUTING TELEMETRY ---")
cursor.execute("SELECT * FROM routing_telemetry ORDER BY timestamp DESC LIMIT 20;")
columns = [col[0] for col in cursor.description]
rows = cursor.fetchall()
print(f"Columns: {columns}")
for row in rows:
    print(dict(zip(columns, row)))

print("\n--- CONFIDENCE TELEMETRY ---")
cursor.execute("SELECT * FROM confidence_telemetry LIMIT 10;")
columns_c = [col[0] for col in cursor.description]
rows_c = cursor.fetchall()
print(f"Columns: {columns_c}")
for row in rows_c:
    print(dict(zip(columns_c, row)))

print("\n--- TRIGGER TELEMETRY ---")
cursor.execute("SELECT * FROM trigger_telemetry LIMIT 20;")
columns_t = [col[0] for col in cursor.description]
rows_t = cursor.fetchall()
print(f"Columns: {columns_t}")
for row in rows_t:
    print(dict(zip(columns_t, row)))

conn.close()
