-- Personal Excel report templates for the statistics constructor.

CREATE TABLE IF NOT EXISTS crm.report_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_login TEXT NOT NULL REFERENCES crm.users(login) ON DELETE CASCADE,
    name TEXT NOT NULL,
    spec JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_login, name)
);

CREATE INDEX IF NOT EXISTS idx_crm_report_templates_user
    ON crm.report_templates (user_login);
