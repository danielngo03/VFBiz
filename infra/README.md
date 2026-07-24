# Platform & SRE workspace

Status: local staging foundation in delivery. `local/compose.yaml` defines the
isolated API/PostGIS, AI/pgvector, Keycloak/PostgreSQL and Redis dependencies;
it is not a production topology.

Planned ownership: environments, workload identity, secret interfaces, network
boundaries, observability, scaling, backup/restore, deployment and incident
runbooks. Provider selection remains undecided until requirements and ownership
are approved.
