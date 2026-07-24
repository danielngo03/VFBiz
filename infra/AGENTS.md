# Infrastructure workspace instructions

Read root `AGENTS.md` and this file. Read `README.md` for scope.

- Infrastructure and production operations are controlled changes.
- No plaintext secret, real account ID or production data enters Git.
- Prefer reversible, immutable changes with health checks, rollback and recovery
  evidence.
- Never deploy, destroy resources or change access without explicit human approval.
- Do not create infrastructure code until an approved work item starts it.
