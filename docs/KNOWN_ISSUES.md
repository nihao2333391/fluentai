# Known Issues and M0 Boundaries

1. PyFluent settings classes are version-specific. The production adapter must keep the Fluent 2025 R2 mapping explicit.
2. `read_case_data()` requires a matching data file; case-only loading must use `read_case()`.
3. Settings writes must be applied through the parent settings object rather than by rebinding a captured child value object.
4. Launched sessions require explicit cleanup behavior; otherwise Fluent child processes can remain after Python exits.
5. `session.connection_properties` contains an ephemeral password. It must never be written to normal logs or committed reports.
6. M0 does not verify save/reopen, packaged sidecar startup, Fluent crash recovery, or real GUI interaction.
7. M0 verifies one Windows installation and one Fluent version only.
8. Arbitrary Python/TUI command execution remains out of scope.