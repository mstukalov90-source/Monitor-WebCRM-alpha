-- Manager review flags for OATI letters (soft-hide stays in DB).

ALTER TABLE webcrm.oati_letters
    ADD COLUMN IF NOT EXISTS review_status TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_by TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS hidden_by TEXT;

ALTER TABLE webcrm.oati_letters
    DROP CONSTRAINT IF EXISTS oati_letters_review_status_check;

ALTER TABLE webcrm.oati_letters
    ADD CONSTRAINT oati_letters_review_status_check
    CHECK (review_status IS NULL OR review_status IN ('approved', 'rejected'));

CREATE INDEX IF NOT EXISTS idx_webcrm_oati_letters_hidden_at
    ON webcrm.oati_letters (hidden_at)
    WHERE hidden_at IS NULL;
