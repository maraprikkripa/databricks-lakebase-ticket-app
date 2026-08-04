"""
One-time setup: creates the tickets / ticket_messages schema in Lakebase
and seeds sample data.

Run locally (needs LAKEBASE_URL resolvable via lakebase.py, i.e. the
Databricks secret scope already configured) or from a Databricks notebook:

    python seed_tickets.py
"""

import lakebase

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    message_id    SERIAL PRIMARY KEY,
    ticket_id     INTEGER NOT NULL REFERENCES tickets(ticket_id),
    message_text  TEXT NOT NULL,
    author        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

SEED_SQL = """
INSERT INTO tickets (title, status, created_by) VALUES
    ('Cannot log in to dashboard', 'open', 'alice@example.com'),
    ('Export button not working', 'in_progress', 'bob@example.com'),
    ('Feature request: dark mode', 'resolved', 'carol@example.com');

INSERT INTO ticket_messages (ticket_id, message_text, author) VALUES
    ((SELECT ticket_id FROM tickets WHERE title = 'Cannot log in to dashboard'),
     'I tried resetting my password but still can''t log in.', 'alice@example.com'),
    ((SELECT ticket_id FROM tickets WHERE title = 'Cannot log in to dashboard'),
     'Can you confirm which browser and OS you''re using?', 'support@example.com'),

    ((SELECT ticket_id FROM tickets WHERE title = 'Export button not working'),
     'Clicking Export just spins forever, no download starts.', 'bob@example.com'),
    ((SELECT ticket_id FROM tickets WHERE title = 'Export button not working'),
     'We''ve reproduced this and are working on a fix.', 'support@example.com'),

    ((SELECT ticket_id FROM tickets WHERE title = 'Feature request: dark mode'),
     'Would love a dark mode option for the dashboard.', 'carol@example.com'),
    ((SELECT ticket_id FROM tickets WHERE title = 'Feature request: dark mode'),
     'Shipped in the latest release - let us know what you think!', 'support@example.com');
"""


def already_seeded() -> bool:
    rows = lakebase.run_query("SELECT COUNT(*) AS n FROM tickets")
    return rows[0]["n"] > 0


def main():
    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            conn.commit()

    if already_seeded():
        print("tickets table already has rows - skipping seed to avoid duplicates.")
        return

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SEED_SQL)
            conn.commit()

    print("Schema created and sample data seeded.")


if __name__ == "__main__":
    main()
