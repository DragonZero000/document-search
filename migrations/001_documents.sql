CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL PRIMARY KEY,
    rubrics      TEXT[]    NOT NULL,
    text         TEXT      NOT NULL,
    created_date TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS documents_created_date_idx ON documents (created_date);
