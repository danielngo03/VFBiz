# Security policy

VFBiz currently provides a staging foundation for the API, AI, Drupal and
client shells. It has no supported production release, production SLA or
approved production-data path.

Do not place vulnerabilities, secrets, production identifiers or customer data
in public issues, chat prompts or repository fixtures. Report suspected security
issues privately to the organization's designated Security owner. A real contact
and response SLA must be added before the repository is opened to contributors.

The staging baseline requires least-privilege access, synthetic fixtures,
redacted logs, dependency and secret scanning, scoped agent writes and human
approval for authentication, PII, AI, contracts, migrations and production
operations. These controls are engineering gates; they are not a claim of legal
or regulatory compliance.

AI agents may analyze only data explicitly approved for their task. They cannot
accept security risk, approve privacy use, authorize production access or close a
security finding on behalf of a human owner.
