# Files

- [Test strategy — fakes, testcontainers, fake issuer, CI-logic and archive suites, gates](test-strategy.md) - What each test suite proves and with which doubles. One fake per port for the application, a temp-dir repository for the git adapter (including byte-deterministic archives), a PostgreSQL container, a fake OIDC issuer around a real server process (including the archive descriptor and download), typer runners for the CLI including the CI logic, gitleaks acquisition and the scaffold script, Harbor's Oracle for the shipped evals, and the static gates run by pre-commit and CI.
