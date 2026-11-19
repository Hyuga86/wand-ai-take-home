"""Run the gateway against a downstream HTTP fixture and verify its boundary."""

import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_hex

from gateway import AuditLog, Gateway, RunContext, TicketAdapter


class GatewayDemo(unittest.TestCase):
    def test_tool_boundary(self):
        credentials = {tenant: token_hex(16) for tenant in ("acme", "globex")}
        received = []

        class Downstream(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                authorization = self.headers.get("Authorization")
                response = {"status": "open", "debug": authorization}
                status_code = 200
                if authorization != f"Bearer {credentials[body['tenant']]}":
                    status_code = 403
                    response = {"error": authorization}
                elif body["ticket_id"] == "T-2":
                    response["status"] = authorization
                elif body["ticket_id"] == "T-3":
                    status_code = 500
                    response = {"error": authorization}
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                received.append((body, authorization))

            def log_message(self, format, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Downstream) as server:
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                endpoint = f"http://127.0.0.1:{server.server_port}/ticket-status"
                with tempfile.TemporaryDirectory() as directory:
                    database = sqlite3.connect(Path(directory) / "audit.sqlite")
                    try:
                        self.verify_scenario(database, endpoint, credentials, received)
                    finally:
                        database.close()
            finally:
                server.shutdown()
                worker.join()

    def verify_scenario(self, database, endpoint, credentials, received):
        gateway = Gateway(TicketAdapter(endpoint, credentials), AuditLog(database))
        run = RunContext("run-1", "acme", "agent-7", "user-42", frozenset({"ticket.status"}))
        restricted = RunContext("run-2", "acme", "agent-8", "user-42", frozenset())
        other_tenant = RunContext(
            "run-3", "globex", "agent-9", "user-56", frozenset({"ticket.status"}),
        )

        # Scripted proposals are the model's entire input to the gateway.
        scenarios = [
            (run, "ticket.status", "acme", "T-1", {"status": "open"}),
            (restricted, "ticket.status", "acme", "T-1", {"error": "tool_denied"}),
            (run, "ticket.status", "globex", "T-1", {"error": "tenant_denied"}),
            (run, "ticket.status", "acme", "invalid", {"error": "invalid_arguments"}),
            (run, "ticket.status", "acme", "T-2", {"error": "invalid_tool_result"}),
            (run, "ticket.status", "acme", "T-3", {"error": "tool_unavailable"}),
            (other_tenant, "ticket.status", "globex", "T-1", {"status": "open"}),
        ]
        model_results = []
        for context, tool, tenant, ticket_id, expected in scenarios:
            result = gateway.call(context, {
                "tool": tool, "arguments": {"tenant": tenant, "ticket_id": ticket_id},
            })
            self.assertEqual(result, expected)
            model_results.append(result)

        dispatched = [("acme", "T-1"), ("acme", "T-2"), ("acme", "T-3"), ("globex", "T-1")]
        self.assertEqual(received, [
            ({"tenant": tenant, "ticket_id": ticket}, f"Bearer {credentials[tenant]}")
            for tenant, ticket in dispatched
        ])
        records = database.execute("""
            SELECT call_id, run_id, tenant_id, agent_id, user_id, tool, outcome
            FROM audit ORDER BY sequence
        """).fetchall()
        self.assertEqual([row[-1] for row in records], [
            "dispatch_authorized", "succeeded", "tool_denied", "tenant_denied",
            "invalid_arguments", "dispatch_authorized", "invalid_tool_result",
            "dispatch_authorized", "tool_unavailable", "dispatch_authorized", "succeeded",
        ])
        self.assertEqual(len({row[0] for row in records}), len(scenarios))
        for intent, completion in ((0, 1), (5, 6), (7, 8), (9, 10)):
            self.assertEqual(records[intent][0], records[completion][0])
        attributed_runs = [run, run, restricted, run, run, run, run, run, run,
                           other_tenant, other_tenant]
        for record, context in zip(records, attributed_runs, strict=True):
            self.assertEqual(record[1:6], (
                context.run_id, context.tenant_id, context.agent_id, context.user_id, "ticket.status",
            ))
        boundary_output = json.dumps({"model": model_results, "audit": records})
        for credential in credentials.values():
            self.assertNotIn(credential, boundary_output)

        database.execute("DROP TABLE audit")
        with self.assertRaises(sqlite3.Error):
            gateway.call(run, {"tool": "ticket.status", "arguments": {
                "tenant": "acme", "ticket_id": "T-4",
            }})
        self.assertEqual(len(received), len(dispatched))

        print("Verified tenant authorization, credential isolation, attribution, and audit-before-dispatch.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
