from framework1.core_services.Request import Request
import re


class TableSearchSortMixin:
    def _extract_join_aliases(self, query) -> set[str]:
        aliases = set()
        for join_sql in getattr(query, "joins", []) or []:
            m = re.search(r"\bJOIN\s+[^\s]+\s+(?:AS\s+)?([A-Za-z_][\w]*)\s+ON\b", str(join_sql), re.IGNORECASE)
            if m:
                aliases.add(m.group(1))
        return aliases

    def _is_column_in_query_scope(self, query, text: str) -> bool:
        if "." not in text:
            return True
        qualifier = text.split(".", 1)[0]
        base_table = str(getattr(query, "__table__", "") or "")
        base_alias = str(getattr(query, "alias", "") or "")
        return qualifier in {base_table, base_alias} or qualifier in self._extract_join_aliases(query)

    def _qualify_column_for_query(self, query, column: str):
        text = str(column).strip()
        if not text:
            return None
        if "." in text:
            return text if self._is_column_in_query_scope(query, text) else None
        if not re.fullmatch(r"[A-Za-z_][\w]*", text):
            return None
        table_name = str(getattr(query, "__table__", "") or "")
        return f"{table_name}.{text}" if table_name else text

    def _resolve_search_mode(self) -> str:
        mode = str(getattr(self, "search_mode", "contains") or "contains").strip().lower()
        if mode not in {"contains", "prefix", "exact", "full_text"}:
            return "contains"
        return mode

    def _build_like_pattern(self, term: str, mode: str) -> str:
        if mode == "prefix":
            return f"{term}%"
        if mode == "exact":
            return term
        return f"%{term}%"

    def _apply_search_term(self, query, searchable_fields: list[str], term: str, mode: str):
        if mode == "full_text":
            # Prefer full-text; gracefully fall back if not supported by current driver/query.
            try:
                if hasattr(query, "where_full_text"):
                    if len(searchable_fields) == 1:
                        return query.where_full_text(
                            searchable_fields[0], term, getattr(self, "full_text_mode", None)
                        )
                    return query.nest(
                        lambda q: [
                            q.or_where_full_text(col, term, getattr(self, "full_text_mode", None))
                            for col in searchable_fields
                        ]
                    )
            except NotImplementedError:
                pass
            mode = "contains"

        return query.where_any_columns(searchable_fields, "LIKE", self._build_like_pattern(term, mode))

    def _apply_sorting(self, query):
        request = Request()
        session_key = f"{self.__class__.__name__}_sort"

        sort_fields = (
            request.input(f"{self.table_name}[sort]", "").split(",")
            if request.has(f"{self.table_name}[sort]")
            else []
        )
        sort_dirs = (
            request.input(f"{self.table_name}[sort_dir]", "").lower().split(",")
            if request.has(f"{self.table_name}[sort_dir]")
            else []
        )

        valid_sort_fields = [f.name() for f in self._get_schema_cached() if getattr(f, "_sortable", False)]
        applied_sort = False

        # Apply user-provided sort
        for idx, field in enumerate(sort_fields):
            field = field.strip()
            if field in valid_sort_fields:
                dir_ = sort_dirs[idx] if idx < len(sort_dirs) else "asc"
                dir_ = dir_ if dir_ in ["asc", "desc"] else "asc"
                qualified = self._qualify_column_for_query(query, field)
                if qualified:
                    query = query.order_by(qualified, dir_)
                    applied_sort = True

        if applied_sort and self.persist_sort:
            # Save to session
            request.session()[session_key] = {
                f"{self.table_name}[sort]": ",".join(sort_fields),
                f"{self.table_name}[sort_dir]": ",".join(sort_dirs),
            }

        # If no sort applied, check session if persist_sort enabled
        if not applied_sort and self.persist_sort:
            session_sort = request.session().get(session_key)
            if session_sort:
                s_fields = session_sort.get(f"{self.table_name}[sort]", "").split(",")
                s_dirs = session_sort.get(f"{self.table_name}[sort_dir]", "").lower().split(",")
                for idx, field in enumerate(s_fields):
                    field = field.strip()
                    if field in valid_sort_fields:
                        dir_ = s_dirs[idx] if idx < len(s_dirs) else "asc"
                        dir_ = dir_ if dir_ in ["asc", "desc"] else "asc"
                        qualified = self._qualify_column_for_query(query, field)
                        if qualified:
                            query = query.order_by(qualified, dir_)
                            applied_sort = True

        # Fallback to default sort
        if not applied_sort:
            default_field, default_dir = self.default_sort()
            if default_field and default_field in valid_sort_fields:
                default_dir = default_dir.lower() if default_dir else "asc"
                qualified = self._qualify_column_for_query(query, default_field)
                if qualified:
                    query = query.order_by(qualified, default_dir)

        return query

    def _apply_search(self, query):
        request = Request()
        session = request.session()
        session_key = f"{self.__class__.__name__}_search"

        search_term = request.input("search")

        if getattr(self, "persist_search", False):
            if search_term is not None:
                if search_term.strip() == "":
                    session.pop(session_key, None)
                    search_term = None
                else:
                    session[session_key] = search_term
            else:
                search_term = session.get(session_key)

        if not search_term:
            return query

        # Merge method + column searchables
        method_fields = []
        if hasattr(self, "searchable") and self.searchable.__func__ is not TableSearchSortMixin.searchable:
            method_fields = self.searchable()

        column_fields = [f.name() for f in self._get_schema_cached() if getattr(f, "_searchable", False)]
        if isinstance(self.search_key, str):
            column_fields.append(self.search_key)
        elif isinstance(self.search_key, list):
            column_fields.extend(self.search_key)
        searchable_fields = []
        for field in list(dict.fromkeys(method_fields + column_fields)):
            qualified = self._qualify_column_for_query(query, field)
            if qualified:
                searchable_fields.append(qualified)

        if not searchable_fields:
            return query

        # Split search into terms
        mode = self._resolve_search_mode()
        min_term_len = int(getattr(self, "search_min_term_length", 1) or 1)
        if mode == "exact":
            terms = [search_term.strip()]
        else:
            terms = [t.strip() for t in search_term.strip().split() if t.strip()]
        terms = [t for t in terms if len(t) >= min_term_len]
        if not terms:
            return query

        # Apply search term strategy per token
        for term in terms:
            query = self._apply_search_term(query, searchable_fields, term, mode)

        return query

    def default_sort(self) -> tuple[str, str]:
        """
        Override this in your table subclass to provide a default sort.
        Example: return ("id", "asc")
        """
        return None, None

    def searchable(self) -> list[str]:
        """
        Override this in your table subclass to provide searchable fields.
        Example: return ["name", "email"]
        """
        return []
