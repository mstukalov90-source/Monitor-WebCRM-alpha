-- CRM users (login/role/work_zones for field CRM app).

CREATE SCHEMA IF NOT EXISTS crm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS crm.users (
    uuid        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    login       TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,
    role        TEXT NOT NULL
        CHECK (role IN ('field', 'office', 'manager', 'admin')),
    work_zones  INTEGER[] NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_crm_users_login
    ON crm.users (login);
CREATE INDEX IF NOT EXISTS idx_crm_users_work_zones
    ON crm.users USING GIN (work_zones);

INSERT INTO crm.users (login, password, role, work_zones) VALUES
    ('vasya', crypt('1234', gen_salt('bf')), 'field',   ARRAY[20, 62]),
    ('gena',  crypt('1234', gen_salt('bf')), 'office',  ARRAY[20, 62]),
    ('lena',  crypt('1234', gen_salt('bf')), 'manager', ARRAY[20, 62]),
    ('admin', crypt('1234', gen_salt('bf')), 'admin',   '{}')
ON CONFLICT (login) DO NOTHING;
