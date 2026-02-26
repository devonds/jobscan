"""Database schema definitions for SQLite storage."""

SCHEMA_VERSION = 1

CREATE_TABLES = """
-- Job postings from Slack channels
CREATE TABLE IF NOT EXISTS slack_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Slack metadata
    message_ts TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    workspace TEXT,
    posted_by_user_id TEXT,
    posted_at TIMESTAMP NOT NULL,

    -- Extracted job data
    company TEXT,
    position TEXT,
    location TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency TEXT DEFAULT 'USD',
    employment_type TEXT,
    work_mode TEXT,

    -- Full content
    raw_message TEXT NOT NULL,
    parsed_description TEXT,
    job_url TEXT,
    scraped_description TEXT,

    -- Skills/requirements (JSON array)
    skills_mentioned TEXT,

    -- Tracking
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied BOOLEAN DEFAULT FALSE,
    applied_at TIMESTAMP,
    match_score REAL,

    -- Unique constraint for deduplication
    UNIQUE(message_ts, channel_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_slack_jobs_channel ON slack_jobs(channel_id);
CREATE INDEX IF NOT EXISTS idx_slack_jobs_company ON slack_jobs(company);
CREATE INDEX IF NOT EXISTS idx_slack_jobs_posted ON slack_jobs(posted_at);
CREATE INDEX IF NOT EXISTS idx_slack_jobs_applied ON slack_jobs(applied);
CREATE INDEX IF NOT EXISTS idx_slack_jobs_work_mode ON slack_jobs(work_mode);

-- Scrape history for incremental fetching
CREATE TABLE IF NOT EXISTS scrape_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    workspace TEXT,
    last_message_ts TEXT NOT NULL,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    messages_processed INTEGER DEFAULT 0,
    jobs_found INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_scrape_history_channel ON scrape_history(channel_id);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""
