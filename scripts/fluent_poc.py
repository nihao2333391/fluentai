"""M0 PyFluent feasibility probe for Fluent AI.

This script is intentionally self-contained and does not import the future
application backend. It proves launch, attach, case loading, settings readback,
write verification, and connection cleanup against a real Fluent session.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = PROJECT_ROOT / ".runtime"
DEFAULT_SESSION_FILE = DEFAULT_RUNTIME_DIR / "fluent_session.json"
DEFAULT_CASE = Path(r"D:\Fluent AI\ansys-runs\compat-smoke-20261021-170520\01_mesh.cas.h5")
DEFAULT_FLUENT_EXE = Path(r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def emit(value: dict[str, Any], prefix: str = "M0_RESULT") -> None:
    print(prefix + " " + json.dumps(value, ensure_ascii=False, default=str), flush=True)


def import_pyfluent() -> Any:
    if os.environ.get("PYFLUENT_FLUENT_ROOT") is None:
        os.environ["PYFLUENT_FLUENT_ROOT"] = str(DEFAULT_FLUENT_EXE.parents[2])
    import ansys.fluent.core as pyfluent

    return pyfluent


def ensure_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} does not exist: {resolved}")
    return resolved


def connection_info(session: Any, *, include_password: bool = False) -> dict[str, Any]:
    props = session.connection_properties
    result = {
        "ip": props.ip,
        "port": props.port,
        "cortex_host": props.cortex_host,
        "cortex_pid": props.cortex_pid,
        "fluent_host_pid": props.fluent_host_pid,
        "inside_container": props.inside_container,
    }
    if include_password:
        result["password"] = props.password
    else:
        result["password_redacted"] = True
    return result


def session_record(session: Any, *, case_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at_utc": utc_now(),
        "fluent_version": str(session.get_fluent_version()),
        "case_path": str(case_path),
        "connection": connection_info(session, include_password=True),
    }


def load_case(session: Any, case_path: Path) -> None:
    session.settings.file.read_case(file_name=str(case_path))


def read_settings(session: Any) -> tuple[dict[str, Any], dict[str, str]]:
    setup = session.settings.setup
    solution = session.settings.solution
    eqs = solution.monitor.residual.equations
    getters: dict[str, Callable[[], Any]] = {
        "solver_time": lambda: setup.general.solver.time.get_state(),
        "viscous_model": lambda: setup.models.viscous.model.get_state(),
        "k_omega_model": lambda: setup.models.viscous.k_omega_model.get_state(),
        "energy_enabled": lambda: setup.models.energy.enabled.get_state(),
        "residual_continuity": lambda: eqs["continuity"].absolute_criteria.get_state(),
        "residual_x_velocity": lambda: eqs["x-velocity"].absolute_criteria.get_state(),
    }
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, getter in getters.items():
        try:
            values[name] = getter()
        except Exception as exc:  # Keep reading the remaining settings.
            errors[name] = f"{type(exc).__name__}: {exc}"
    return values, errors


def verify_write_and_restore(session: Any) -> dict[str, Any]:
    eqs = session.settings.solution.monitor.residual.equations
    target = eqs["continuity"].absolute_criteria
    before = float(target.get_state())
    replacement = before + (0.0001 if abs(before) < 1.0 else 0.01)
    result: dict[str, Any] = {
        "setting": "solution.monitor.residual.equations.continuity.absolute_criteria",
        "before": before,
        "replacement": replacement,
        "write_verified": False,
        "restored": False,
    }
    try:
        eqs["continuity"].absolute_criteria = replacement
        after_write = float(eqs["continuity"].absolute_criteria.get_state())
        result["after_write"] = after_write
        result["write_verified"] = math.isclose(after_write, replacement, rel_tol=1e-12, abs_tol=1e-15)
        if not result["write_verified"]:
            raise RuntimeError(f"Write verification failed: expected {replacement}, got {after_write}")
    finally:
        try:
            eqs["continuity"].absolute_criteria = before
            restored = float(eqs["continuity"].absolute_criteria.get_state())
            result["after_restore"] = restored
            result["restored"] = math.isclose(restored, before, rel_tol=1e-12, abs_tol=1e-15)
        except Exception as exc:
            result["restore_error"] = f"{type(exc).__name__}: {exc}"
    return result


def run_checks(session: Any, *, mode: str, case_path: Path) -> dict[str, Any]:
    load_case(session, case_path)
    settings, read_errors = read_settings(session)
    write_result = verify_write_and_restore(session)
    successful = len(settings)
    passed = successful >= 5 and write_result.get("write_verified") and write_result.get("restored")
    return {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "mode": mode,
        "created_at_utc": utc_now(),
        "fluent_version": str(session.get_fluent_version()),
        "case_path": str(case_path),
        "settings_read": settings,
        "settings_read_count": successful,
        "settings_read_errors": read_errors,
        "write_verification": write_result,
        "connection": connection_info(session),
    }


def launch_session(args: argparse.Namespace, pyfluent: Any, *, ui_mode: str) -> Any:
    fluent_exe = ensure_file(Path(args.fluent_exe), "Fluent executable")
    runtime = Path(args.runtime_dir).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    return pyfluent.launch_fluent(
        fluent_path=str(fluent_exe),
        product_version=args.product_version,
        dimension=3,
        precision="double",
        processor_count=1,
        mode="solver",
        ui_mode=ui_mode,
        py=False,
        cwd=str(runtime),
        start_timeout=args.start_timeout,
        start_transcript=False,
        cleanup_on_exit=True,
        start_watchdog=False,
    )


def close_launched_session(session: Any) -> str | None:
    try:
        session.exit()
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def connect_from_record(pyfluent: Any, session_file: Path) -> tuple[Any, dict[str, Any]]:
    record = json.loads(ensure_file(session_file, "session file").read_text(encoding="utf-8"))
    connection = record["connection"]
    session = pyfluent.connect_to_fluent(
        ip=connection["ip"],
        port=int(connection["port"]),
        password=connection.get("password"),
        cleanup_on_exit=False,
        start_transcript=False,
    )
    return session, record


def cmd_env_check(args: argparse.Namespace) -> int:
    pyfluent = import_pyfluent()
    from importlib import metadata

    fluent_exe = ensure_file(Path(args.fluent_exe), "Fluent executable")
    case_path = ensure_file(Path(args.case), "case file")
    result = {
        "status": "passed",
        "checked_at_utc": utc_now(),
        "python": sys.version,
        "python_executable": sys.executable,
        "ansys_fluent_core_version": metadata.version("ansys-fluent-core"),
        "pyfluent_version": getattr(pyfluent, "__version__", "unknown"),
        "fluent_executable": str(fluent_exe),
        "case_file": str(case_path),
        "case_bytes": case_path.stat().st_size,
        "launch_api": hasattr(pyfluent, "launch_fluent"),
        "attach_api": hasattr(pyfluent, "connect_to_fluent"),
    }
    write_json(Path(args.report), result)
    emit(result)
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    pyfluent = import_pyfluent()
    case_path = ensure_file(Path(args.case), "case file")
    report: dict[str, Any] = {"status": "failed", "mode": "launch", "started_at_utc": utc_now()}
    session = None
    try:
        session = launch_session(args, pyfluent, ui_mode=args.ui_mode)
        report.update(run_checks(session, mode="launch", case_path=case_path))
        report["ui_mode"] = args.ui_mode
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if session is not None:
            report["close_error"] = close_launched_session(session)
    report["finished_at_utc"] = utc_now()
    write_json(Path(args.report), report)
    emit(report)
    return 0 if report.get("status") == "passed" else 1


def cmd_launch_hold(args: argparse.Namespace) -> int:
    pyfluent = import_pyfluent()
    case_path = ensure_file(Path(args.case), "case file")
    session_file = Path(args.session_file).resolve()
    stop_file = Path(args.stop_file).resolve()
    report: dict[str, Any] = {"status": "failed", "mode": "launch_hold", "started_at_utc": utc_now()}
    session = None
    try:
        session = launch_session(args, pyfluent, ui_mode=args.ui_mode)
        report.update(run_checks(session, mode="launch_hold", case_path=case_path))
        report["ui_mode"] = args.ui_mode
        write_json(session_file, session_record(session, case_path=case_path))
        report["session_file"] = str(session_file)
        emit(report, "M0_LAUNCH_READY")
        deadline = time.monotonic() + args.hold_seconds
        while time.monotonic() < deadline:
            if stop_file.exists():
                report["stop_reason"] = "stop_file"
                break
            time.sleep(1)
        else:
            report["stop_reason"] = "timeout"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if session is not None:
            report["close_error"] = close_launched_session(session)
        try:
            session_file.unlink(missing_ok=True)
        except OSError:
            pass
    report["finished_at_utc"] = utc_now()
    write_json(Path(args.report), report)
    emit(report, "M0_LAUNCH_FINISHED")
    return 0 if report.get("status") == "passed" else 1


def cmd_attach(args: argparse.Namespace) -> int:
    pyfluent = import_pyfluent()
    case_path = ensure_file(Path(args.case), "case file")
    report: dict[str, Any] = {"status": "failed", "mode": "attach", "started_at_utc": utc_now()}
    try:
        session, record = connect_from_record(pyfluent, Path(args.session_file))
        report["attached_to_fluent_version"] = record.get("fluent_version")
        report["healthy"] = bool(session.is_active())
        report.update(run_checks(session, mode="attach", case_path=case_path))
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    report["finished_at_utc"] = utc_now()
    write_json(Path(args.report), report)
    emit(report)
    return 0 if report.get("status") == "passed" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fluent AI M0 PyFluent feasibility probe")
    parser.add_argument("--fluent-exe", default=str(DEFAULT_FLUENT_EXE))
    parser.add_argument("--product-version", default="25.2.0")
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--start-timeout", type=int, default=300)
    sub = parser.add_subparsers(dest="command", required=True)

    env = sub.add_parser("env-check", help="Validate Python, PyFluent, Fluent, and case paths")
    env.add_argument("--report", default=str(PROJECT_ROOT / "docs" / "poc" / "reports" / "env_check.json"))
    env.set_defaults(func=cmd_env_check)

    launch = sub.add_parser("launch", help="Launch Fluent, load a case, and verify settings I/O")
    launch.add_argument("--ui-mode", default="no_gui", choices=["no_gui", "no_graphics", "hidden_gui", "gui"])
    launch.add_argument("--report", default=str(PROJECT_ROOT / "docs" / "poc" / "reports" / "launch.json"))
    launch.set_defaults(func=cmd_launch)

    hold = sub.add_parser("launch-hold", help="Launch Fluent and keep it alive for attach testing")
    hold.add_argument("--ui-mode", default="no_gui", choices=["no_gui", "no_graphics", "hidden_gui", "gui"])
    hold.add_argument("--session-file", default=str(DEFAULT_SESSION_FILE))
    hold.add_argument("--stop-file", default=str(DEFAULT_RUNTIME_DIR / "stop_session"))
    hold.add_argument("--hold-seconds", type=int, default=300)
    hold.add_argument("--report", default=str(PROJECT_ROOT / "docs" / "poc" / "reports" / "launch_hold.json"))
    hold.set_defaults(func=cmd_launch_hold)

    attach = sub.add_parser("attach", help="Attach to a session recorded by launch-hold")
    attach.add_argument("--session-file", default=str(DEFAULT_SESSION_FILE))
    attach.add_argument("--report", default=str(PROJECT_ROOT / "docs" / "poc" / "reports" / "attach.json"))
    attach.set_defaults(func=cmd_attach)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        emit({"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}}, "M0_FATAL")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())