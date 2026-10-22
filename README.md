# Fluent AI

## M0 - Fluent feasibility gate - PASSED

This repository currently contains only the M0 feasibility probe. No Electron or FastAPI application code is created until the real Fluent integration gate passes.

### Verified local runtime

- Fluent: `D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe`
- Python: `D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe`
- PyFluent: `ansys-fluent-core 0.42.1`
- Fluent product version: `25.2.0`

The existing Python 3.12 environment is reused because it already contains the locally verified PyFluent runtime. This supersedes the initial plan to create a new Python 3.10 environment.

### Commands

Environment and path validation:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\fluent_poc.py' env-check
```

Launch, load case, read at least five settings, write one setting, verify readback, and restore it:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\fluent_poc.py' launch --ui-mode no_gui
```

Keep a launched session alive for attach testing:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\fluent_poc.py' launch-hold --hold-seconds 300
```

Attach from a second process:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\fluent_poc.py' attach
```

Reports are written to `docs\poc\reports\`.
### M0 gate check

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\check_m0_reports.py'
```

Expected result: `M0_GATE_PASSED`.

See `docs\poc\fluent-2025R2.md` for the full evidence and limitations.