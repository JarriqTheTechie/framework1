# Table DSL Module Layout

This folder contains the Table DSL split into focused modules. Public API remains
available via `framework1.dsl.Table`.

## Modules

- `core.py`:
  Table base class and mixin composition. High-level orchestration.
- `fields.py`:
  `Field` and `TextColumn` classes (column configuration).
- `master_detail.py`:
  `MasterDetailRow` and master-detail helpers.
- `filters.py`:
  Filter application and grouped filter handling.
- `search_sort.py`:
  Search and sorting behavior.
- `pagination.py`:
  Pagination logic and response handling.
- `export.py`:
  Excel export handling.
- `render.py`:
  HTML rendering helpers (header, body, pagination).
- `routes.py`:
  Table-related routes (`TableExportExcel`, `TableDeleteBulk`).
- `utils.py`:
  Shared helpers (`record_to_dict`).

## Notes

- Keep public API names intact in `framework1/dsl/Table.py`.
- Add new features in the smallest module that matches the responsibility.
- Avoid cross-module imports unless required to prevent circular dependencies.
