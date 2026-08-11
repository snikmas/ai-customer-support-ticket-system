# Archived UI artifacts

This directory preserves generated or retired frontend artifacts that are no
longer part of the active application tree.

- `legacy-controls/` contains the retired `UnsupportedButton` component and
  its test. They are preserved for recoverability after the active frontend
  cleanup; the active source and test globs no longer include them.
- `mockup-sandbox/` contains the original generated ResolveAI mockup sandbox.
  It is reference material only and is not imported by the application.

These files are intentionally archived rather than silently discarded.
