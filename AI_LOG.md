# AI usage log

Tools used in the recorded session include OpenAI Codex (GPT-6) and its local PowerShell and Python tooling.

| What was asked | What AI produced | What happened next |
|---|---|---|
| Read the brief and propose a plan before writing code. | Summarized the deliverables and proposed a gateway slice, an architecture, and a time budget. | Vikram reviewed the plan, approved it, and asked Codex to implement it. |
| Implement the approved plan. | Built a Python gateway, local downstream fixture, executable boundary assertions, and Markdown deliverables. | The implementation uses a trusted in-process run harness and a real downstream HTTP boundary. The README scopes the claim to the tested interface. |
| Verify the boundary. | Added cases for a missing grant, cross-tenant input, invalid arguments, reflected credentials, and failure to commit an audit intent. | The Python demo passed, including a rerun with resource warnings enabled as errors. Compose configuration validated, and the container run was blocked by an unavailable Docker daemon. |
| Review the submission against the brief. | Extended the demo to exercise successful calls for two tenants and checked the six submission files in a fresh directory. | The clean-copy run verified credential selection for both tenants and checked that audit attribution matched each run. |

## Revisions made during implementation

- The initial plan called for an allowlisted response. The implementation also validates allowed values because the downstream fixture can reflect a secret into the status field itself.
- The initial plan described logging a call. The implementation commits dispatch intent first and tests database failure before dispatch, so execution cannot go ahead without an audit record.
- The initial plan proposed a containerized local run. The implementation also supports a single standard-library Python command, preserving the HTTP boundary while making it independently runnable without Docker.

## My role and where AI helped

I decided to review the implementation plan before authorizing any code. I set that approval checkpoint myself, approved the gateway slice, and requested a final pass against the brief. Codex proposed the architecture, implemented the demo, drafted the documentation, and ran the checks.

I approved the technical direction and asked Codex to verify the result. The revisions above came from Codex during implementation. Its clean-copy test checked observable behavior at the gateway boundary. It compared the credentials received by the downstream fixture for two tenants, checked that denied calls never arrived, and inspected the model-visible results and audit rows for leaked credentials.

AI's clearest contribution was turning the broad credential-isolation claim into concrete failure cases. The downstream fixture echoed the credential in an extra field, in the allowed status field, and in an HTTP error. That gave me specific evidence to discuss about why output validation needs to check values as well as field names.
