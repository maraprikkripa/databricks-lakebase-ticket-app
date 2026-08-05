# Day 1 Homework Submission — Lakebase Support Ticket App

## 1. Submission Links

- **Databricks App URL:** `https://dataexpert-ticket-support-app-7474656818519820.aws.databricksapps.com`
- **Source code repository:** `https://github.com/maraprikkripa/databricks-lakebase-ticket-app`

## 2. Lakebase Schema Evidence

### DDL (from `app.py`'s `ensure_tables()`)

```sql
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    description TEXT,
    priority    TEXT NOT NULL DEFAULT 'medium',
    category    TEXT NOT NULL DEFAULT 'other',
    environment TEXT NOT NULL DEFAULT 'production',
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    message_id    SERIAL PRIMARY KEY,
    ticket_id     INTEGER NOT NULL REFERENCES tickets(ticket_id),
    message_text  TEXT NOT NULL,
    author        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- **Primary keys:** `tickets.ticket_id` (SERIAL), `ticket_messages.message_id` (SERIAL)
- **Foreign key:** `ticket_messages.ticket_id` → `tickets.ticket_id` (enforced via `REFERENCES`)
- `priority`, `category`, `environment`, `description`, `resolved_at` are additional columns beyond the minimum spec, added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for the bonus priority/category challenges.

### Screenshot to capture (manual step)

Open **Catalog Explorer** → your Lakebase instance → `databricks_postgres` → `public` schema → `tickets` and `ticket_messages` → **Sample Data** tab, and screenshot both. This is required for submission and can't be captured from here — it needs to come from your own browser session.

## 3. Application ↔ Lakebase: SQL/API Calls Per Feature

All database access goes through `lakebase.py`, which:
1. Uses the **Databricks SDK** (`WorkspaceClient().secrets.get_secret(scope="database", key="lakebase-url")`) to fetch the Postgres connection string from a Databricks secret (never hardcoded).
2. Opens a `psycopg2` connection to Lakebase (native Postgres role, static password) and runs plain SQL.

| App feature | Route | SQL executed |
|---|---|---|
| View all tickets | `GET /` | `SELECT ticket_id, title, status, priority, category, created_by, created_at FROM tickets [WHERE ...] ORDER BY created_at DESC` |
| View one ticket + its messages | `GET /tickets/<id>` | `SELECT ... FROM tickets WHERE ticket_id = %s` then `SELECT ... FROM ticket_messages WHERE ticket_id = %s ORDER BY created_at ASC` |
| Create a ticket | `POST /tickets` | `INSERT INTO tickets (title, description, status, priority, category, environment, created_by) VALUES (...) RETURNING ticket_id` |
| Add a message | `POST /tickets/<id>/messages` | `INSERT INTO ticket_messages (ticket_id, message_text, author) VALUES (...)` |
| Update status | `POST /tickets/<id>/status` | `UPDATE tickets SET status = %s, resolved_at = CASE WHEN %s = 'resolved' THEN now() ELSE NULL END WHERE ticket_id = %s` |
| Update priority | `POST /tickets/<id>/priority` | `UPDATE tickets SET priority = %s WHERE ticket_id = %s` |
| Update category | `POST /tickets/<id>/category` | `UPDATE tickets SET category = %s WHERE ticket_id = %s` |
| Delete a ticket | `POST /tickets/<id>/delete` | `DELETE FROM ticket_messages WHERE ticket_id = %s` then `DELETE FROM tickets WHERE ticket_id = %s` |

No application data is hardcoded — every page load queries Lakebase directly.

## 4. Persistence Verification

I ran the exact SQL from the routes above directly against Lakebase to verify end-to-end persistence (create → message → status update → re-query, simulating a refresh):

```
=== STEP 1: CREATE TICKET ===
Inserted ticket_id=33

=== STEP 2: ADD MESSAGE ===
Message inserted.

=== STEP 3: UPDATE STATUS to resolved ===
Status updated to resolved.

=== STEP 4: RE-QUERY (simulating 'refresh the app') ===
tickets row: {'ticket_id': 33, 'title': 'VERIFICATION DEMO - safe to delete',
  'status': 'resolved', 'created_by': 'verify@example.com',
  'created_at': 2026-08-05 21:24:17+00:00, 'description': 'Persistence check for submission',
  'priority': 'low', 'category': 'other', 'environment': 'dev',
  'resolved_at': 2026-08-05 21:24:17+00:00}
ticket_messages rows: [{'message_id': 59, 'ticket_id': 33,
  'message_text': 'This is a persistence verification message.',
  'author': 'verify@example.com', 'created_at': 2026-08-05 21:24:17+00:00}]

=== CLEANUP ===
Demo ticket removed (so it wouldn't clutter the real data for screenshots).
```

The status update correctly stamped `resolved_at`, and both rows persisted exactly as inserted — confirming Lakebase is genuinely being read from and written to, not an in-memory mock.

### To also demonstrate this yourself in the browser (for your own screenshot):

1. Open the app URL, click **+ New ticket**, create one (note the title)
2. Click into it, add a message, then change its status to `resolved`
3. **Refresh the page** — confirm the message and new status are still there
4. Open the Lakebase SQL editor and run:
   ```sql
   SELECT * FROM tickets WHERE title = '<your title>';
   SELECT * FROM ticket_messages WHERE ticket_id = <that ticket's id>;
   ```
5. Screenshot both the app view and the query result side by side

## 5. Reflection

Going into this, I'd never touched Lakebase or built a Databricks App before, so this was very much a learn-by-doing exercise — set up the free workspace, fork the starter repo, and figure out the rest as I hit walls. The most confusing moment was when my app kept crashing after I added new columns, and it took a while to realize the tables I'd created through the SQL editor belonged to my own login, not the separate database role my app actually connects with — once I understood that Lakebase is a real Postgres database with real ownership rules, not just a Databricks-flavored abstraction, the fix made sense. What stood out compared to a normal analytics table is how immediate everything feels: I'd click "create ticket" and a second later it's a real row I could query — no waiting on a batch job, no separate pipeline, just write and read straight away. By the end, going from a blank workspace to a deployed app with a working database, filters, and charts stopped feeling like magic and started feeling like a repeatable process — and using Claude alongside Databricks' own Genie assistant made a real difference, since I could ask "why did this fail" the moment something broke instead of getting stuck. I'm walking away genuinely comfortable putting together a small Databricks + Lakebase app on my own now, and curious to see how AI assistants like Genie fit into the more advanced agent-building days still ahead in the bootcamp.

## 6. Bonus Challenges Completed

- ✅ Ticket priority (`low`/`medium`/`high`) and category (6 data-platform-themed categories)
- ✅ Filtering by status, priority, category, and environment
- ✅ Input validation (required fields, allow-listed enum values server-side)
- ✅ Ticket statistics (stat tiles + tickets-by-category bar chart + tickets-by-priority doughnut chart + 14-day trend line chart)
- ✅ Delete functionality with a JS confirmation step
- ✅ Visual design (branded header, colored badges, sidebar navigation, responsive stat cards)
