# Files

- [Test strategy — fake adapters, testcontainers, fake issuer, gates](test-strategy.md) - Which layer each test suite measures and how it isolates it. Core tests drive the application through fake adapters with no clock; adapter tests use a real git repository and a throwaway PostgreSQL from testcontainers; HTTP tests run the real server process against a fake OIDC issuer; CLI tests run the commands end to end; pyright strict and the altera-rules gates run before every commit and in CI.
