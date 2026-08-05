# Lakebase Support Ticket App

Day 1 bootcamp homework: an internal support system where users can create tickets and add messages to them, backed entirely by Databricks Lakebase.

**Live app:** `https://dataexpert-ticket-support-app-7474656818519820.aws.databricksapps.com`
**Full submission writeup (DDL, SQL/API mapping, persistence verification, reflection):** [SUBMISSION.md](SUBMISSION.md)

## Key files

- [`app.py`](app.py) - the Flask app itself: every route, the SQL for each one, and the schema (`ensure_tables()`)
- [`lakebase.py`](lakebase.py) - the only file that talks to Lakebase: fetches the connection string from a Databricks secret, then plain `psycopg2`
- [`seed_tickets.py`](seed_tickets.py) - one-off script that creates the schema and seeds sample tickets/messages
- [`setup_secrets.py`](setup_secrets.py) - one-time script to store the Lakebase URL as a Databricks secret
- [`app.yaml`](app.yaml) - Databricks App deployment config
- [`templates/`](templates) - `base.html` (shared layout/sidebar), `index.html` (ticket list, stat cards, analytics charts), `ticket.html` (detail + status/priority/category updates), `new_ticket.html` (create form)

## How to run

**Locally:**
```bash
cp .env.example .env          # fill in LAKEBASE_URL
pip install -r requirements.txt
python seed_tickets.py        # creates tables + sample data (safe to re-run)
python app.py                 # http://localhost:8000
```

**As a Databricks App:**
1. One-time: run `setup_secrets.py` from a Databricks notebook (`%sh python setup_secrets.py`) to store the Lakebase URL as secret `database/lakebase-url`
2. Create a Databricks App with this repo as its Git source (reads `app.yaml` automatically)
3. Deploy — `databricks apps deploy <app-name> --profile <profile>` or via the Apps UI
4. Run `seed_tickets.py` once (via a notebook) if the tables aren't already seeded

## Schema

```sql
tickets (
  ticket_id SERIAL PRIMARY KEY, title, status, created_by, created_at,
  description, priority, category, environment, resolved_at
)
ticket_messages (
  message_id SERIAL PRIMARY KEY, ticket_id -> tickets.ticket_id (FK),
  message_text, author, created_at
)
```

## Endpoints

- `GET /` - list tickets (filterable by `?status=`, `?priority=`, `?category=`, `?environment=`), stat cards, analytics charts (`#analytics`)
- `GET /tickets/new` - create-ticket form
- `GET /tickets/<id>` - ticket detail: messages, status/priority/category update forms, delete
- `POST /tickets` - create a ticket
- `POST /tickets/<id>/messages` - add a message
- `POST /tickets/<id>/status` - update status (stamps `resolved_at` when set to `resolved`)
- `POST /tickets/<id>/priority` - update priority
- `POST /tickets/<id>/category` - update category
- `POST /tickets/<id>/delete` - delete a ticket and its messages
- `GET /healthz` - health check
