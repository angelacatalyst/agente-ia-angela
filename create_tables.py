"""
Run this once to create all tables in Neon PostgreSQL.
Usage:
    set DATABASE_URL=postgresql://neondb_owner:npg_xAt3LDKC9Thq@ep-spring-lab-aykq3msc.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require
    python create_tables.py
"""
import os, psycopg2

url = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_xAt3LDKC9Thq@ep-spring-lab-aykq3msc.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require")

SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    agent_module VARCHAR(64) NOT NULL,
    qbo_realm_id VARCHAR(64),
    meta JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    tool_calls JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qbo_tokens (
    realm_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    module VARCHAR(64) NOT NULL,
    action VARCHAR(128) NOT NULL,
    payload JSONB DEFAULT '{}',
    result_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- Add company_name column if it doesn't exist (safe to run multiple times)
ALTER TABLE qbo_tokens ADD COLUMN IF NOT EXISTS company_name VARCHAR(255);
"""

print("Connecting to Neon...")
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute(SQL)
conn.commit()
cur.close()
conn.close()
print("✅ All tables created successfully!")
