# Lakebase Support Ticket App

Day 1 bootcamp homework: an internal support system where users can create tickets and add messages to them, backed entirely by Databricks Lakebase.

## Files

- `app.py` - Flask app: ticket list, ticket detail, create ticket, add message, update status
- `lakebase.py` - Lakebase connection helper (single `LAKEBASE_URL` secret, psycopg2 + SQLAlchemy)
- `seed_tickets.py` - creates the schema and seeds sample tickets/messages
- `setup_secrets.py` - one-time script to store the Lakebase URL as a Databricks secret
- `app.yaml` - Databricks App deployment config
- `templates/` - `index.html` (ticket list + create form), `ticket.html` (messages + status update)

## Schema

```sql
tickets (ticket_id, title, status, created_by, created_at)
ticket_messages (message_id, ticket_id -> tickets.ticket_id, message_text, author, created_at)
```

## Setup

### 1. Store the Lakebase secret (skip if already done for another app in this workspace)

```
%sh python setup_secrets.py
```
from a Databricks notebook, pasting your Lakebase connection URL when prompted.

### 2. Local dev

```bash
cp .env.example .env   # then fill in LAKEBASE_URL
pip install -r requirements.txt
python seed_tickets.py   # creates tables + sample data
python app.py
```

### 3. Deploy

1. Create a Git folder in Databricks pointing at this repo
2. Create a Databricks App, source = this Git folder (reads `app.yaml` automatically)
3. Deploy, then run `python seed_tickets.py` once (via a notebook) to seed sample data if not already done

## Endpoints

- `GET /` - list all tickets, create-ticket form
- `GET /tickets/<id>` - view a ticket's messages, add-message form, status update form
- `POST /tickets` - create a new ticket
- `POST /tickets/<id>/messages` - add a message to a ticket
- `POST /tickets/<id>/status` - update a ticket's status
- `GET /healthz` - health check
