-- Ghosts of Wikipedia: MariaDB schema. Needs MariaDB 11.7+ (VECTOR); developed for mariadb:lts (12.3).
-- Load:  docker compose exec -T mariadb mariadb -ughosts -pghosts ghosts < db/schema.sql
-- All timestamps are UTC: every connection runs SET time_zone = '+00:00'.

-- Every saved version of every article, without its text (dataset M, 862,076 rows).
-- Powers the coordination score, the edit sparkline and the global numbers.
CREATE TABLE IF NOT EXISTS revision (
  rev_id     INT UNSIGNED NOT NULL PRIMARY KEY,
  page_id    INT UNSIGNED NOT NULL,
  parent_id  INT UNSIGNED,
  ts         DATETIME(6)  NOT NULL,            -- when it was saved (UTC)
  user       VARCHAR(255),                     -- user name, IP or temporary account
  anonymous  BOOL NOT NULL DEFAULT 0,          -- never show `user` when this is 1
  comment    TEXT,                             -- the edit summary
  minor      BOOL NOT NULL DEFAULT 0,
  sha1       CHAR(31),
  bytes      INT UNSIGNED,
  is_revert  BOOL NOT NULL DEFAULT 0,          -- text equals an earlier, non-parent version
  KEY page_ts (page_id, ts),
  KEY user_ts (user, ts)
) CHARACTER SET utf8mb4;

-- One row per article: title, and how many ghosts haunt it.
CREATE TABLE IF NOT EXISTS article (
  page_id     INT UNSIGNED NOT NULL PRIMARY KEY,
  title_fi    VARCHAR(255) NOT NULL,
  title_en    VARCHAR(255),
  versions    INT UNSIGNED,
  first_edit  DATETIME(6),
  last_edit   DATETIME(6),
  ghost_count INT UNSIGNED NOT NULL DEFAULT 0
) CHARACTER SET utf8mb4;

-- One row per unique sentence text.
CREATE TABLE IF NOT EXISTS sentence (
  hash    BINARY(20) NOT NULL PRIMARY KEY,     -- SHA-1 of the normalised, case-folded text
  text_fi TEXT NOT NULL,
  text_en TEXT                                 -- Gemini translation, filled lazily (Person 3)
) CHARACTER SET utf8mb4;

-- Every life of every sentence on every page. History rows (row_end in the past) are ghosts;
-- they are written with Wikipedia's real edit times via system_versioning_insert_history.
CREATE TABLE IF NOT EXISTS sentence_life (
  page_id        INT UNSIGNED NOT NULL,
  hash           BINARY(20)   NOT NULL,
  section        VARCHAR(255),                 -- heading it stood under
  prev_hash      BINARY(20),                   -- the sentence before it: where to draw the ghost
  pos            INT UNSIGNED,                 -- its position (now, or when it died)
  born_rev       INT UNSIGNED NOT NULL,
  died_rev       INT UNSIGNED,                 -- NULL while alive
  kind           ENUM('alive','erased','rewritten','typo','reverted') NOT NULL,
  successor_hash BINARY(20),                   -- "reincarnated as"
  similarity     FLOAT,                        -- to the successor
  row_start TIMESTAMP(6) GENERATED ALWAYS AS ROW START INVISIBLE,
  row_end   TIMESTAMP(6) GENERATED ALWAYS AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end),
  PRIMARY KEY (page_id, hash),
  KEY start_key (page_id, row_start),          -- MariaDB's demo: AS OF on old dates needs this
  KEY hash_key (hash)                          -- moves across articles, search joins
) CHARACTER SET utf8mb4 WITH SYSTEM VERSIONING;

-- The years a sentence talks about (event time), next to when Wikipedia said it (system time).
CREATE TABLE IF NOT EXISTS sentence_event (
  hash       BINARY(20) NOT NULL PRIMARY KEY,
  event_from DATE NOT NULL,                    -- 1 Jan of the first year it mentions
  event_to   DATE NOT NULL,                    -- 1 Jan of the year after the last one
  PERIOD FOR event_time (event_from, event_to)
);

-- EmbeddingGemma vectors, one per unique sentence (Person 3 fills it).
CREATE TABLE IF NOT EXISTS sentence_vec (
  hash BINARY(20) NOT NULL PRIMARY KEY,
  emb  VECTOR(768) NOT NULL,
  VECTOR INDEX (emb) M=16 DISTANCE=cosine
);

-- Precomputed keyframes for the time-lapse: the ordered living sentences at each moment.
CREATE TABLE IF NOT EXISTS article_frame (
  page_id INT UNSIGNED NOT NULL,
  ts      DATETIME(6)  NOT NULL,
  rev_id  INT UNSIGNED NOT NULL,
  hashes  JSON NOT NULL,                       -- ["ab12…", …] in reading order
  edits   INT UNSIGNED NOT NULL DEFAULT 0,     -- edits since the previous frame
  deaths  INT UNSIGNED NOT NULL DEFAULT 0,     -- sentences that died since the previous frame
  PRIMARY KEY (page_id, ts)
);

-- Sentences that left a page but live on in another one ("moved to ...", not a ghost).
-- History rows can't be updated, so moves live in their own table (pipeline/moves.py).
CREATE TABLE IF NOT EXISTS sentence_move (
  page_id    INT UNSIGNED NOT NULL,
  hash       BINARY(20)   NOT NULL,
  died_rev   INT UNSIGNED NOT NULL,
  to_page_id INT UNSIGNED NOT NULL,
  PRIMARY KEY (page_id, hash, died_rev)
);

-- Coordination score per removal (Person 3 fills it).
CREATE TABLE IF NOT EXISTS coordination (
  page_id   INT UNSIGNED NOT NULL,
  hash      BINARY(20)   NOT NULL,
  died_rev  INT UNSIGNED NOT NULL,
  score     TINYINT UNSIGNED NOT NULL,         -- 0-100, percentile vs random editor groups
  evidence  JSON NOT NULL,                     -- [{"label","value","explain"}]
  PRIMARY KEY (page_id, hash, died_rev)
);
