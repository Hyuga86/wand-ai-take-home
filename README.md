# Agentic orchestration take-home

The [design](DESIGN.md) describes the Kubernetes orchestration framework. The demo implements the tool gateway for one read-only ticket status tool.

## Run the demo

From the repository root, with Python 3.11 or newer:

```sh
python -B demo.py
```

With Docker Compose:

```sh
docker compose run --rm demo
```

The Python command uses the standard library and an ephemeral loopback port. Compose runs the same test in a container with external networking disabled. Both commands exit nonzero if an assertion fails.

## What the test checks

- Allowed calls from two tenants send their respective tenant credentials over HTTP, return the approved status, and record intent and completion under the same attributed call ID.
- An agent without the grant, a cross-tenant proposal, and malformed arguments each produce an audited rejection. The downstream request list contains only the authorized calls.
- Extra response fields, a credential reflected into the allowed status field, and an HTTP error that echoes the credential do not expose the synthetic secret in model-visible results or audit rows.
- If the gateway cannot commit an audit intent, the downstream call never starts.

## Slice choice and limits

The gateway is where the framework turns untrusted model output into a credentialed action. The demo checks whether that boundary survives both invalid proposals and a downstream service that reflects its authorization header. The fixture showed why filtering field names alone is insufficient. An allowed field also needs a type and value contract. The next slice would test durable recovery after a downstream write succeeds and the worker loses its response.

The gateway, policy checks, HTTP request, result validation, and SQLite writes are real. A scripted model generates proposals, an in-process trusted harness supplies the run context, and a loopback HTTP fixture stands in for the ticket service. The test uses random synthetic credentials and a temporary audit database. The local harness and gateway share a process, so the tested model boundary is the proposal and result interface. The production design maps the harness to a Kubernetes worker and places the gateway behind authenticated workload transport.

The demo covers one read-only operation and one local test process. Production workload authentication, managed secrets, durable retries, rich tool output handling, sandbox isolation, and throughput are design work or follow-up validation. See the [AI usage log](AI_LOG.md) for the recorded implementation decisions.
