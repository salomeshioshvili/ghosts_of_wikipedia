"""Shared settings and helpers for the pipeline and the API. Nothing to run here."""
import csv, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_M = os.path.join(ROOT, "data", "m")                 # the 16 Parquet files of dataset M
HERO_LIST = os.path.join(ROOT, "data", "hero_articles.tsv")
SCHEMA = os.path.join(ROOT, "db", "schema.sql")

# --- .env next to the repo root overrides the defaults (same as docker-compose.yml) ---
_env = os.path.join(ROOT, ".env")
if os.path.exists(_env):
    for line in open(_env, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.strip().split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

DB = dict(host=os.environ.get("DB_HOST", "127.0.0.1"),
          port=int(os.environ.get("DB_PORT", 3307)),
          user=os.environ.get("DB_USER", "ghosts"),
          password=os.environ.get("DB_PASSWORD", "ghosts"),
          database=os.environ.get("DB_NAME", "ghosts"))


class _QmarkCursor:
    """PyMySQL cursor that accepts the mariadb connector's '?' placeholders."""
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=None):
        return self._cur.execute(sql.replace("%", "%%").replace("?", "%s") if params else sql, params)

    def executemany(self, sql, rows):
        return self._cur.executemany(sql.replace("%", "%%").replace("?", "%s"), rows)

    def __getattr__(self, name):
        return getattr(self._cur, name)


def connect():
    """A MariaDB connection that speaks UTC (row_start/row_end are TIMESTAMPs).
    Uses the `mariadb` connector if installed, else pure-Python PyMySQL (same '?' placeholders)."""
    try:
        import mariadb
        con = mariadb.connect(**DB, autocommit=False)
        cur = con.cursor()
    except ImportError:
        import pymysql
        con = pymysql.connect(host=DB["host"], port=DB["port"], user=DB["user"], password=DB["password"],
                              database=DB["database"], charset="utf8mb4", autocommit=False,
                              max_allowed_packet=64 * 1024 * 1024)
        cur = _QmarkCursor(con.cursor())
    cur.execute("SET time_zone = '+00:00'")
    return con, cur


def apply_schema(cur, drop=()):
    """Run db/schema.sql (CREATE TABLE IF NOT EXISTS ...). `drop` = tables to drop first."""
    for table in drop:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
    sql = open(SCHEMA, encoding="utf-8").read()
    sql = re.sub(r"--[^\n]*", "", sql)                    # comments may contain ';'
    for statement in sql.split(";"):
        if statement.strip():
            cur.execute(statement)


def hero_pages():
    """The 50 articles of MariaDB's time-machine demo (all include the 1918 war, page 1150)."""
    with open(HERO_LIST, encoding="utf-8") as f:
        return [int(row["page_id"]) for row in csv.DictReader(f, delimiter="\t")]


def batched_executemany(cur, sql, rows, max_bytes=8_000_000, size_of=None):
    """executemany in batches that stay under MariaDB's packet limit."""
    size_of = size_of or (lambda r: sum(len(x) if isinstance(x, (str, bytes)) else 8 for x in r))
    batch, size = [], 0
    for row in rows:
        s = size_of(row)
        if batch and size + s > max_bytes:
            cur.executemany(sql, batch)
            batch, size = [], 0
        batch.append(row)
        size += s
    if batch:
        cur.executemany(sql, batch)
