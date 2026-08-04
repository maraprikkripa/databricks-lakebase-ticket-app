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

from flask import Flask, jsonify, render_template, request, redirect, url_for

import lakebase
from databricks.sdk import WorkspaceClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ticket-app")

app = Flask(__name__)
_w = WorkspaceClient()

VALID_STATUSES = ("open", "in_progress", "resolved")


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


@app.route("/")
def index():
    """List all tickets."""
    tickets = lakebase.run_query(
        "SELECT ticket_id, title, status, created_by, created_at "
        "FROM tickets ORDER BY created_at DESC"
    )
    return render_template("index.html", tickets=tickets, statuses=VALID_STATUSES)


@app.route("/tickets/<int:ticket_id>")
def view_ticket(ticket_id):
    """View a single ticket and its messages."""
    tickets = lakebase.run_query(
        "SELECT ticket_id, title, status, created_by, created_at "
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
        "ticket.html", ticket=tickets[0], messages=messages, statuses=VALID_STATUSES
    )


@app.route("/tickets", methods=["POST"])
def create_ticket():
    """Create a new ticket."""
    title = request.form.get("title", "").strip()
    if not title:
        return "Title is required", 400

    lakebase.run_write(
        "INSERT INTO tickets (title, status, created_by) VALUES (%s, %s, %s)",
        (title, "open", _current_user_email()),
    )
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
    """Update a ticket's status."""
    status = request.form.get("status", "")
    if status not in VALID_STATUSES:
        return f"Invalid status: {status}", 400

    lakebase.run_write(
        "UPDATE tickets SET status = %s WHERE ticket_id = %s",
        (status, ticket_id),
    )
    return redirect(url_for("view_ticket", ticket_id=ticket_id))


ensure_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
