-- Create the strava database if it doesn't exist (handled by POSTGRES_DB env var)
-- Create the greens table
CREATE TABLE IF NOT EXISTS greens (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255),
    num INTEGER DEFAULT 0,
    grid_count INTEGER DEFAULT 0,
    lastupdate TIMESTAMP
);

-- Create an index on num for faster leaderboard queries
CREATE INDEX IF NOT EXISTS idx_greens_num ON greens(num DESC);

