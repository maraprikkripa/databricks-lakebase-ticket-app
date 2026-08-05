"""
Databricks App: Lakebase-powered support ticket system.
- Serves a small Flask UI + API
- Reads/writes tickets and ticket_messages to Lakebase via lakebase.py

Run locally:
    python app.py
Deploy as a Databricks App using app.yaml.
"""

import logging
import os
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template, request, redirect, url_for

import lakebase
from databricks.sdk import WorkspaceClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ticket-app")

app = Flask(__name__)
_w = WorkspaceClient()

VALID_STATUSES = ("open", "in_progress", "resolved")
VALID_PRIORITIES = ("low", "medium", "high")
VALID_CATEGORIES = (
    "pipeline_failure",
    "data_quality",
    "access_request",
    "schema_change",
    "performance",
    "other",
)
VALID_ENVIRONMENTS = ("dev", "staging", "production")


def ensure_tables():
    """Create the tickets and ticket_messages tables if they don't exist yet."""
    lakebase.run_write(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id   SERIAL PRIMARY KEY,
            title       TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'open',
            created_by  TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Added after the initial schema. The connecting role may not own a table
    # created earlier via a different identity (e.g. the SQL editor) - in that
    # case ALTER fails with a permission error; skip rather than crash the app.
    try:
        lakebase.run_write("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS description TEXT")
    except Exception:
        logger.warning("Could not add description column - continuing without it", exc_info=True)
    try:
        lakebase.run_write(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'medium'"
        )
    except Exception:
        logger.warning("Could not add priority column - continuing without it", exc_info=True)
    try:
        lakebase.run_write(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'other'"
        )
    except Exception:
        logger.warning("Could not add category column - continuing without it", exc_info=True)
    try:
        lakebase.run_write(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'production'"
        )
    except Exception:
        logger.warning("Could not add environment column - continuing without it", exc_info=True)
    try:
        lakebase.run_write("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ")
    except Exception:
        logger.warning("Could not add resolved_at column - continuing without it", exc_info=True)
    lakebase.run_write(
        """
        CREATE TABLE IF NOT EXISTS ticket_messages (
            message_id    SERIAL PRIMARY KEY,
            ticket_id     INTEGER NOT NULL REFERENCES tickets(ticket_id),
            message_text  TEXT NOT NULL,
            author        TEXT NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _current_user_email() -> str:
    """
    Resolve the current user's email for created_by/author fields.

    Databricks Apps inject the logged-in user's identity via the
    X-Forwarded-Email header on every request. Fall back to the Databricks
    SDK's current_user API for local development where that header isn't set.
    """
    header_email = request.headers.get("X-Forwarded-Email")
    if header_email:
        return header_email
    return _w.current_user.me().user_name


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


def get_status_counts():
    """Return ticket counts per status plus a total, for the sidebar/stat cards."""
    rows = lakebase.run_query("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status")
    counts = {s: 0 for s in VALID_STATUSES}
    for r in rows:
        counts[r["status"]] = r["n"]
    counts["total"] = sum(counts.values())
    return counts


def get_priority_counts():
    """Return ticket counts per priority, for the sidebar/right panel."""
    rows = lakebase.run_query("SELECT priority, COUNT(*) AS n FROM tickets GROUP BY priority")
    counts = {p: 0 for p in VALID_PRIORITIES}
    for r in rows:
        counts[r["priority"]] = r["n"]
    return counts


def get_category_counts():
    """Return ticket counts per category, for the sidebar and analytics chart."""
    rows = lakebase.run_query("SELECT category, COUNT(*) AS n FROM tickets GROUP BY category")
    counts = {c: 0 for c in VALID_CATEGORIES}
    for r in rows:
        counts[r["category"]] = r["n"]
    return counts


def get_recent_activity(limit=5):
    """Return the most recent messages across all tickets, for the right panel."""
    return lakebase.run_query(
        "SELECT tm.message_id, tm.message_text, tm.author, tm.created_at, "
        "       t.ticket_id, t.title "
        "FROM ticket_messages tm "
        "JOIN tickets t ON t.ticket_id = tm.ticket_id "
        "ORDER BY tm.created_at DESC LIMIT %s",
        (limit,),
    )


def get_avg_resolution_hours():
    """Average time from creation to resolution, in hours, across resolved tickets."""
    rows = lakebase.run_query(
        "SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600) AS avg_hours "
        "FROM tickets WHERE resolved_at IS NOT NULL"
    )
    avg_hours = rows[0]["avg_hours"] if rows else None
    return round(float(avg_hours), 1) if avg_hours is not None else None


def get_top_category():
    """Category with the most tickets, for the 'at a glance' panel."""
    counts = get_category_counts()
    if not any(counts.values()):
        return None
    top = max(counts, key=counts.get)
    return top.replace("_", " ").title()


def get_tickets_per_day(days=14):
    """Daily ticket counts for the last N days, as (labels, values) for a line chart."""
    # `days` is always an internal constant, never user input - safe to inline.
    rows = lakebase.run_query(
        f"SELECT date_trunc('day', created_at) AS day, COUNT(*) AS n "
        f"FROM tickets WHERE created_at >= now() - interval '{days} days' "
        f"GROUP BY day ORDER BY day"
    )
    counts_by_day = {r["day"].date(): r["n"] for r in rows}

    today = datetime.utcnow().date()
    labels, values = [], []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        labels.append(day.strftime("%b %d"))
        values.append(counts_by_day.get(day, 0))
    return labels, values


def common_context():
    """Shared context every page needs for the sidebar and right panel."""
    return {
        "statuses": VALID_STATUSES,
        "priorities": VALID_PRIORITIES,
        "categories": VALID_CATEGORIES,
        "environments": VALID_ENVIRONMENTS,
        "counts": get_status_counts(),
        "priority_counts": get_priority_counts(),
        "category_counts": get_category_counts(),
        "recent_activity": get_recent_activity(),
        "avg_resolution_hours": get_avg_resolution_hours(),
        "top_category": get_top_category(),
    }


@app.route("/")
def index():
    """List tickets, optionally filtered by status, priority, and/or category."""
    status_filter = request.args.get("status")
    if status_filter not in VALID_STATUSES:
        status_filter = None

    priority_filter = request.args.get("priority")
    if priority_filter not in VALID_PRIORITIES:
        priority_filter = None

    category_filter = request.args.get("category")
    if category_filter not in VALID_CATEGORIES:
        category_filter = None

    where_clauses = []
    params = []
    if status_filter:
        where_clauses.append("status = %s")
        params.append(status_filter)
    if priority_filter:
        where_clauses.append("priority = %s")
        params.append(priority_filter)
    if category_filter:
        where_clauses.append("category = %s")
        params.append(category_filter)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    tickets = lakebase.run_query(
        f"SELECT ticket_id, title, status, priority, category, created_by, created_at "
        f"FROM tickets {where_sql} ORDER BY created_at DESC",
        tuple(params) if params else None,
    )

    return render_template(
        "index.html",
        tickets=tickets,
        current_view=status_filter or "all",
        current_priority=priority_filter or "all",
        current_category=category_filter or "all",
        **common_context(),
    )


@app.route("/tickets/new")
def new_ticket_form():
    """Dedicated create-ticket page."""
    return render_template(
        "new_ticket.html",
        current_view=None,
        current_priority=None,
        current_category=None,
        **common_context(),
    )


@app.route("/analytics")
def analytics():
    """Charts: tickets over time, by category, by priority, avg resolution time."""
    chart_labels, chart_values = get_tickets_per_day()
    ctx = common_context()
    return render_template(
        "analytics.html",
        current_view=None,
        current_priority=None,
        current_category=None,
        chart_labels=chart_labels,
        chart_values=chart_values,
        category_labels=[c.replace("_", " ").title() for c in VALID_CATEGORIES],
        category_values=[ctx["category_counts"][c] for c in VALID_CATEGORIES],
        priority_labels=[p.capitalize() for p in VALID_PRIORITIES],
        priority_values=[ctx["priority_counts"][p] for p in VALID_PRIORITIES],
        **ctx,
    )


@app.route("/tickets/<int:ticket_id>")
def view_ticket(ticket_id):
    """View a single ticket and its messages."""
    tickets = lakebase.run_query(
        "SELECT ticket_id, title, description, status, priority, category, "
        "       environment, created_by, created_at, resolved_at "
        "FROM tickets WHERE ticket_id = %s",
        (ticket_id,),
    )
    if not tickets:
        return "Ticket not found", 404

    messages = lakebase.run_query(
        "SELECT message_id, message_text, author, created_at "
        "FROM ticket_messages WHERE ticket_id = %s ORDER BY created_at ASC",
        (ticket_id,),
    )
    return render_template(
        "ticket.html",
        ticket=tickets[0],
        messages=messages,
        current_view=None,
        current_priority=None,
        current_category=None,
        **common_context(),
    )


@app.route("/tickets", methods=["POST"])
def create_ticket():
    """Create a new ticket and go straight to its detail page."""
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    email = request.form.get("email", "").strip()
    priority = request.form.get("priority", "medium")
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    category = request.form.get("category", "other")
    if category not in VALID_CATEGORIES:
        category = "other"
    environment = request.form.get("environment", "production")
    if environment not in VALID_ENVIRONMENTS:
        environment = "production"

    if not title:
        return "Title is required", 400
    if not email:
        return "Email is required", 400

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tickets "
                "(title, description, status, priority, category, environment, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING ticket_id",
                (title, description or None, "open", priority, category, environment, email),
            )
            new_id = cur.fetchone()["ticket_id"]
            conn.commit()
    return redirect(url_for("view_ticket", ticket_id=new_id))


@app.route("/tickets/<int:ticket_id>/delete", methods=["POST"])
def delete_ticket(ticket_id):
    """Delete a ticket and all of its messages."""
    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ticket_messages WHERE ticket_id = %s", (ticket_id,))
            cur.execute("DELETE FROM tickets WHERE ticket_id = %s", (ticket_id,))
            conn.commit()
    return redirect(url_for("index"))


@app.route("/tickets/<int:ticket_id>/messages", methods=["POST"])
def add_message(ticket_id):
    """Add a message to an existing ticket."""
    message_text = request.form.get("message_text", "").strip()
    if not message_text:
        return "Message text is required", 400

    lakebase.run_write(
        "INSERT INTO ticket_messages (ticket_id, message_text, author) "
        "VALUES (%s, %s, %s)",
        (ticket_id, message_text, _current_user_email()),
    )
    return redirect(url_for("view_ticket", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/status", methods=["POST"])
def update_status(ticket_id):
    """Update a ticket's status. Stamps/clears resolved_at to track resolution time."""
    status = request.form.get("status", "")
    if status not in VALID_STATUSES:
        return f"Invalid status: {status}", 400

    lakebase.run_write(
        "UPDATE tickets SET status = %s, "
        "resolved_at = CASE WHEN %s = 'resolved' THEN now() ELSE NULL END "
        "WHERE ticket_id = %s",
        (status, status, ticket_id),
    )
    return redirect(url_for("view_ticket", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/category", methods=["POST"])
def update_category(ticket_id):
    """Update a ticket's category."""
    category = request.form.get("category", "")
    if category not in VALID_CATEGORIES:
        return f"Invalid category: {category}", 400

    lakebase.run_write(
        "UPDATE tickets SET category = %s WHERE ticket_id = %s",
        (category, ticket_id),
    )
    return redirect(url_for("view_ticket", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/priority", methods=["POST"])
def update_priority(ticket_id):
    """Update a ticket's priority."""
    priority = request.form.get("priority", "")
    if priority not in VALID_PRIORITIES:
        return f"Invalid priority: {priority}", 400

    lakebase.run_write(
        "UPDATE tickets SET priority = %s WHERE ticket_id = %s",
        (priority, ticket_id),
    )
    return redirect(url_for("view_ticket", ticket_id=ticket_id))


ensure_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
