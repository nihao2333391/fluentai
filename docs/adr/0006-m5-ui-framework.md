# ADR 0006: Ant Design application shell and UI state

- Status: accepted
- Date: 2026-10-22

## Context

M5 needs a stable, responsive application shell that can host later business workflows without each page inventing its own navigation, theme, localization, or status handling.

## Decision

### Routing

- React Router 7 provides a hash router for Electron file and development URLs.
- The shell has four top-level destinations:
  - create automation
  - my automations
  - my models
  - settings
- Unknown routes redirect to automation creation.

### Design system

- Ant Design 5 supplies components, layouts, accessibility behavior, and form primitives.
- A shared theme configuration defines primary colors, radii, typography, and component tokens.
- CSS variables distinguish light and dark surfaces outside Ant Design's token system.
- The React 19 compatibility patch is loaded before rendering.

### UI state

- Zustand stores theme and language preferences.
- Preferences persist through Zustand middleware under `fluent-ai-ui-preferences`.
- Theme modes are light, dark, and system.
- The system mode responds to `prefers-color-scheme` changes.
- Sidecar state remains runtime-only and is not persisted.

### Localization

- i18next and react-i18next provide Chinese and English resources.
- Ant Design locale providers switch with the application language.
- A test enforces identical resource key sets.

### Status surfaces

- The global header displays active job count and FastAPI sidecar status.
- Sidecar details expose version, PID, port, and restart action in a popover.
- Error and unavailable states are visible without blocking unrelated routes.

### Page states

Reusable components provide loading, empty, error, retry, and desktop-bridge permission states.

## Consequences

- Later business pages can focus on domain workflows rather than shell infrastructure.
- Theme and language are consistent across Ant Design and custom CSS.
- The current bundle is large because Ant Design and icons are eagerly included; route-level code splitting should be considered during hardening.
- Business forms and real automation/model tables remain future work.
