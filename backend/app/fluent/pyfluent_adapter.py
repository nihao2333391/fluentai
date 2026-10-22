"""PyFluent implementation of the FluentAdapter contract."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal, cast

from app.domain import (
    FluentConnectionConfig,
    FluentOperationReport,
    FluentStatus,
    PresetDocument,
    PresetItem,
    PresetValue,
    SettingWriteResult,
)
from app.fluent.catalog import FLUENT_252_CATALOG, FluentSettingCatalog
from app.fluent.comparison import preset_values_equal


def _debug(message: str) -> None:
    if os.environ.get("FLUENT_AI_DEBUG") == "1":
        print(f"[fluent-debug] {message}", file=sys.stderr, flush=True)


class PyFluentAdapter:
    """Fluent 2025 R2 adapter with readback verification and rollback."""

    def __init__(
        self,
        *,
        catalog: FluentSettingCatalog = FLUENT_252_CATALOG,
        pyfluent_module: Any | None = None,
        session: Any | None = None,
        connection_mode: Literal["launch", "attach"] | None = None,
    ) -> None:
        self.catalog = catalog
        self._pyfluent_module = pyfluent_module
        self._session = session
        self._connection_mode = connection_mode

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        _debug(f"connect start mode={config.mode}")
        if self._session is not None and self._is_active():
            self.disconnect()

        pyfluent = self._pyfluent_module or self._load_pyfluent()
        _debug("pyfluent module ready")
        if config.mode == "launch":
            launch_kwargs: dict[str, Any] = {
                "product_version": config.product_version,
                "dimension": 3,
                "precision": "double",
                "processor_count": config.processor_count,
                "mode": "solver",
                "ui_mode": config.ui_mode,
                "py": False,
                "start_timeout": config.start_timeout,
                "cleanup_on_exit": config.cleanup_on_exit,
                "start_watchdog": False,
                "start_transcript": False,
            }
            if config.fluent_path:
                launch_kwargs["fluent_path"] = config.fluent_path
            _debug("launch_fluent start")
            self._session = pyfluent.launch_fluent(**launch_kwargs)
            _debug("launch_fluent returned")
        else:
            if config.server_info_file:
                self._session = pyfluent.connect_to_fluent(
                    server_info_file_name=config.server_info_file,
                    password=config.password,
                    cleanup_on_exit=False,
                    start_transcript=False,
                )
            else:
                if config.port is None:
                    raise ValueError("Attach mode requires a port or server-info file.")
                self._session = pyfluent.connect_to_fluent(
                    ip=config.host,
                    port=config.port,
                    password=config.password,
                    cleanup_on_exit=False,
                    start_transcript=False,
                )

        self._connection_mode = config.mode
        status = self.status()
        _debug(f"connect complete connected={status.connected}")
        return status

    def disconnect(self) -> None:
        session = self._session
        mode = self._connection_mode
        self._session = None
        self._connection_mode = None
        if session is None:
            return
        if mode == "launch":
            session.exit()

    def status(self) -> FluentStatus:
        session = self._session
        if session is None or not self._is_active():
            return FluentStatus(connected=False, mode=self._connection_mode)

        version: str | None = None
        try:
            version = str(session.get_fluent_version())
        except Exception:
            version = None

        host: str | None = None
        port: int | None = None
        pid: int | None = None
        properties = getattr(session, "connection_properties", None)
        if properties is not None:
            host = getattr(properties, "ip", None) or getattr(properties, "cortex_host", None)
            raw_port = getattr(properties, "port", None)
            port = int(raw_port) if raw_port is not None else None
            raw_pid = getattr(properties, "fluent_host_pid", None) or getattr(
                properties, "cortex_pid", None
            )
            pid = int(raw_pid) if raw_pid is not None else None

        return FluentStatus(
            connected=True,
            mode=self._connection_mode,
            version=version,
            pid=pid,
            host=host,
            port=port,
        )

    def load_case(self, file_path: str) -> None:
        session = self._ensure_session()
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Fluent case file does not exist: {path}")
        session.settings.file.read_case(file_name=str(path))

    def save_case(self, file_path: str) -> None:
        session = self._ensure_session()
        path = Path(file_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        session.settings.file.write_case(file_name=str(path))

    def read_settings(self, setting_ids: list[str]) -> dict[str, PresetValue]:
        session = self._ensure_session()
        return self.catalog.read(session, setting_ids)

    def write_settings(self, items: list[PresetItem]) -> FluentOperationReport:
        return self._write_items(items, operation="write")

    def apply_preset(self, preset: PresetDocument) -> FluentOperationReport:
        return self._write_items(preset.items, operation="apply")

    def _write_items(
        self,
        items: list[PresetItem],
        *,
        operation: Literal["write", "apply"],
    ) -> FluentOperationReport:
        session = self._ensure_session()
        if not items:
            return FluentOperationReport(operation=operation, status="success")

        prepared: dict[str, tuple[Any, PresetValue]] = {}
        old_values: dict[str, PresetValue] = {}
        validation_errors: dict[str, str] = {}
        for item in items:
            if item.setting_id in prepared or item.setting_id in validation_errors:
                validation_errors[item.setting_id] = "Duplicate setting in one operation."
                continue
            try:
                definition = self.catalog.get(item.setting_id)
                normalized = definition.validate(item.value)
                old_value = definition.read(session)
            except Exception as exc:
                validation_errors[item.setting_id] = f"{type(exc).__name__}: {exc}"
                continue
            prepared[item.setting_id] = (definition, normalized)
            old_values[item.setting_id] = old_value

        if validation_errors:
            validation_results = [
                SettingWriteResult(
                    setting_id=item.setting_id,
                    expected=item.value,
                    actual=None,
                    success=False,
                    message=validation_errors.get(
                        item.setting_id, "No settings were written because validation failed."
                    ),
                )
                for item in items
            ]
            return FluentOperationReport(
                operation=operation,
                status="failed",
                results=validation_results,
            )

        results: list[SettingWriteResult] = []
        for item in items:
            definition, normalized = prepared[item.setting_id]
            try:
                definition.write(session, normalized)
                actual = definition.read(session)
                success = preset_values_equal(normalized, actual)
                results.append(
                    SettingWriteResult(
                        setting_id=item.setting_id,
                        expected=normalized,
                        actual=actual,
                        success=success,
                        message="" if success else "Readback did not match the requested value.",
                    )
                )
            except Exception as exc:
                actual = self._safe_read(definition, session)
                results.append(
                    SettingWriteResult(
                        setting_id=item.setting_id,
                        expected=normalized,
                        actual=actual,
                        success=False,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )

        if all(result.success for result in results):
            return FluentOperationReport(
                operation=operation,
                status="success",
                results=results,
            )

        rollback_results: list[SettingWriteResult] = []
        for setting_id, old_value in reversed(list(old_values.items())):
            definition, _ = prepared[setting_id]
            try:
                definition.write(session, old_value)
                actual = definition.read(session)
                success = preset_values_equal(old_value, actual)
                rollback_results.append(
                    SettingWriteResult(
                        setting_id=setting_id,
                        expected=old_value,
                        actual=actual,
                        success=success,
                        message="" if success else "Rollback readback did not match.",
                    )
                )
            except Exception as exc:
                rollback_results.append(
                    SettingWriteResult(
                        setting_id=setting_id,
                        expected=old_value,
                        actual=self._safe_read(definition, session),
                        success=False,
                        message=f"Rollback failed: {type(exc).__name__}: {exc}",
                    )
                )

        return FluentOperationReport(
            operation=operation,
            status="failed",
            results=results,
            rollback_attempted=True,
            rollback_succeeded=all(result.success for result in rollback_results),
            rollback_results=rollback_results,
        )

    def _ensure_session(self) -> Any:
        if self._session is None or not self._is_active():
            raise RuntimeError("Fluent is not connected.")
        return self._session

    def _is_active(self) -> bool:
        if self._session is None:
            return False
        try:
            return bool(self._session.is_active())
        except Exception:
            return True

    @staticmethod
    def _safe_read(definition: Any, session: Any) -> PresetValue:
        try:
            return cast(PresetValue, definition.read(session))
        except Exception:
            return None

    @staticmethod
    def _load_pyfluent() -> Any:
        import ansys.fluent.core as pyfluent  # type: ignore[import-untyped]

        return pyfluent
