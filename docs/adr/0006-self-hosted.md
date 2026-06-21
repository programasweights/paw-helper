# ADR 0006: Self-hosted per deployment, not a hosted service

Status: accepted

## Context
Others want to run a helper for their own site. We could host a multi-tenant
service or ship a framework they self-host.

## Decision
Ship `paw_helper` as a pip-installable framework that each deployer self-hosts
against their own content pack, compiling their own programs (their own PAW
program IDs) through the hosted PAW API.

## Consequences
- No tenant isolation, billing, or abuse surface for us to operate.
- Each deployer controls their content, programs, CORS, and logs.
- The repo must make self-hosting easy: quickstart, deploy templates
  (systemd/nginx), `paw-helper validate`, and a minimal example content pack.
