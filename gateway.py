"""Authorize model tool proposals and dispatch approved calls."""

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4


@dataclass(frozen=True)
class RunContext:
    run_id: str
    tenant_id: str
    agent_id: str
    user_id: str
    granted_tools: frozenset[str]


class AuditLog:
    def __init__(self, database: sqlite3.Connection):
        self.database = database
        with database:
            database.execute("""
                CREATE TABLE IF NOT EXISTS audit (
                    sequence INTEGER PRIMARY KEY,
                    call_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    outcome TEXT NOT NULL
                )
            """)

    def record(self, run: RunContext, call_id: str, tool: str, outcome: str):
        with self.database:
            self.database.execute(
                """INSERT INTO audit
                   (call_id, recorded_at, run_id, tenant_id, agent_id, user_id, tool, outcome)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (call_id, datetime.now(UTC).isoformat(), run.run_id, run.tenant_id,
                 run.agent_id, run.user_id, tool, outcome),
            )


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TicketAdapter:
    def __init__(self, endpoint: str, credentials: dict[str, str]):
        self.endpoint = endpoint
        self.credentials = credentials.copy()
        self.client = build_opener(ProxyHandler({}), RejectRedirects())

    def read_status(self, tenant: str, ticket_id: str) -> dict:
        credential = self.credentials.get(tenant)
        if credential is None:
            return {"error": "credential_unavailable"}

        request = Request(
            self.endpoint,
            data=json.dumps({"tenant": tenant, "ticket_id": ticket_id}).encode(),
            headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"},
        )
        try:
            with self.client.open(request, timeout=2) as response:
                body = response.read(4097)
            if len(body) > 4096:
                return {"error": "invalid_tool_result"}
            decoded = json.loads(body)
        except HTTPError as error:
            error.close()
            return {"error": "tool_unavailable"}
        except (URLError, OSError):
            return {"error": "tool_unavailable"}
        except (ValueError, RecursionError):
            return {"error": "invalid_tool_result"}

        status = decoded.get("status") if isinstance(decoded, dict) else None
        if status not in ("open", "closed"):
            return {"error": "invalid_tool_result"}
        return {"status": status}


class Gateway:
    def __init__(self, adapter: TicketAdapter, audit: AuditLog):
        self.adapter = adapter
        self.audit = audit

    def call(self, run: RunContext, proposal: object) -> dict:
        call_id = uuid4().hex
        if not isinstance(proposal, dict):
            self.audit.record(run, call_id, "unknown", "invalid_arguments")
            return {"error": "invalid_arguments"}

        tool = "ticket.status"
        if proposal.get("tool") != tool or tool not in run.granted_tools:
            label = tool if proposal.get("tool") == tool else "unknown"
            self.audit.record(run, call_id, label, "tool_denied")
            return {"error": "tool_denied"}

        arguments = proposal.get("arguments")
        if not isinstance(arguments, dict) or set(arguments) != {"tenant", "ticket_id"}:
            self.audit.record(run, call_id, tool, "invalid_arguments")
            return {"error": "invalid_arguments"}
        if arguments["tenant"] != run.tenant_id:
            self.audit.record(run, call_id, tool, "tenant_denied")
            return {"error": "tenant_denied"}
        ticket_id = arguments["ticket_id"]
        if not isinstance(ticket_id, str) or not re.fullmatch(r"T-[0-9]{1,10}", ticket_id):
            self.audit.record(run, call_id, tool, "invalid_arguments")
            return {"error": "invalid_arguments"}

        self.audit.record(run, call_id, tool, "dispatch_authorized")
        result = self.adapter.read_status(run.tenant_id, ticket_id)
        self.audit.record(run, call_id, tool, result.get("error", "succeeded"))
        return result
