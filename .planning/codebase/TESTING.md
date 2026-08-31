# Testing Practices

**Analysis date:** 2026-08-31

## Current State

- The repository contains no test files, test directories, or test configuration.
- There is no `tests/` layout, no `test_*.py` modules, and no inline doctest coverage.
- No Python test framework such as `pytest` or `unittest` is configured.
- `flake.nix` includes no project test runner, test dependency, check output, or CI-facing test command.
- The locally built third-party `O365` package explicitly sets `doCheck = false`, so its upstream checks do not run during the Nix build.
- No continuous-integration configuration is present.
- No coverage tool, threshold, report format, or coverage artifact is configured.

## Testability of the Current Script

- Importing `read_mailbox.py` immediately reads environment variables and may raise `ValueError`.
- With configuration present, importing the module constructs an `O365.Account`, reads the filesystem token backend, and may authenticate over the network.
- Import continues by selecting the `automations@vegetationlink.com.au` mailbox, opening `Inbox`, and enumerating messages.
- These import-time side effects prevent isolated unit tests from importing helpers safely.
- Configuration, authentication, mailbox selection, message retrieval, and rendering have no function boundaries to target independently.
- The fixed mailbox address and folder name cannot be substituted through function arguments.
- The unused `SCOPES` and `count` values have no tests that would reveal their divergence from the actual execution path.

## Framework and Layout

- There is no established framework or repository-specific test naming convention to preserve.
- When tests are introduced, place them under a top-level `tests/` directory rather than beside the operational script.
- Mirror production responsibilities with focused modules such as configuration, account construction, and message processing before creating corresponding tests.
- Use one consistent runner and expose it through the Nix development environment so local and automated execution match.
- Add the chosen runner to the Python environment in `flake.nix`; currently the environment contains only `python-o365`.
- Provide a single documented command that runs all tests from the repository root.

## Unit Test Patterns Needed

- Configuration tests should cover all required variables present and each variable missing individually.
- Validation assertions should verify the exact environment-variable names actually consumed by `read_mailbox.py`.
- Account-construction tests should verify credentials, tenant ID, auth flow, and token backend without contacting Microsoft Graph.
- Authentication tests should cover already-authenticated and unauthenticated accounts.
- Mailbox tests should verify the configured resource and `Inbox` folder selection through injected collaborators.
- Message-processing tests should use small fake message objects and assert safe output or transformation behavior.
- A regression test should ensure a single retrieval path is used instead of issuing redundant `get_messages()` calls.

## Mocking and Fixtures

- No mocks, fixtures, factories, snapshots, or recorded HTTP responses currently exist.
- External O365 calls should be replaced by injected fakes or mocks in unit tests.
- Environment manipulation should be scoped per test and restored automatically to avoid leaking credentials or state between cases.
- Token tests should use a temporary directory and synthetic token content; never read `my_token.txt` or `token/my_token.txt`.
- Network access should be disabled or treated as a failure in the default unit-test suite.
- Reusable fixtures should describe roles (`authenticated_account`, `inbox_folder`) rather than mirror incidental SDK construction details.

## Integration and End-to-End Coverage

- No integration, contract, smoke, or end-to-end tests are present.
- A future live Microsoft Graph smoke test must be opt-in because it requires credentials, network access, tenant permissions, and a real mailbox.
- Live tests should use a dedicated test mailbox rather than `automations@vegetationlink.com.au`.
- Separate deterministic tests from credentialed tests with an explicit marker or command so ordinary development never triggers mailbox access.
- Integration assertions should minimize message content exposure and avoid printing full mailbox objects in logs.

## Coverage and Quality Gates

- Current effective project coverage is unmeasured because no tests or coverage configuration exist.
- There are no pass thresholds for lines, branches, mutation score, typing, linting, or formatting.
- Initial coverage should prioritize configuration failures and authentication branches, which contain the only explicit decision logic today.
- Add coverage reporting only after import-time behavior is removed; otherwise module import itself will require unsafe external setup.
- Nix checks should eventually execute the deterministic suite, but no such check exists in the current flake.

## Running Tests

- There is currently no valid project test command to run.
- `nix develop` enters the declared development shell but does not execute validation.
- `nix flake check` has no project test check defined in `flake.nix`.
- Running `python read_mailbox.py` is an operational mailbox action, not a test, and depends on injected secrets and external service availability.
- Do not use the production script as a smoke-test substitute because it may authenticate, access real mail, and disclose message metadata.

---

**Refreshed:** 2026-08-31
