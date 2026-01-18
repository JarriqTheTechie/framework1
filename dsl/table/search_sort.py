from framework1.core_services.Request import Request


class TableSearchSortMixin:
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

        valid_sort_fields = [f.name() for f in self.schema() if getattr(f, "_sortable", False)]
        applied_sort = False

        # Apply user-provided sort
        for idx, field in enumerate(sort_fields):
            field = field.strip()
            if field in valid_sort_fields:
                dir_ = sort_dirs[idx] if idx < len(sort_dirs) else "asc"
                dir_ = dir_ if dir_ in ["asc", "desc"] else "asc"
                query = query.order_by(field, dir_)
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
                        query = query.order_by(field, dir_)
                        applied_sort = True

        # Fallback to default sort
        if not applied_sort:
            default_field, default_dir = self.default_sort()
            if default_field and default_field in valid_sort_fields:
                default_dir = default_dir.lower() if default_dir else "asc"
                query = query.order_by(default_field, default_dir)

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

        column_fields = [f.name() for f in self.schema() if getattr(f, "_searchable", False)]
        if isinstance(self.search_key, str):
            column_fields.append(self.search_key)
        elif isinstance(self.search_key, list):
            column_fields.extend(self.search_key)
        searchable_fields = list(dict.fromkeys(method_fields + column_fields))

        if not searchable_fields:
            return query

        # Split search into terms
        terms = [t.strip() for t in search_term.strip().split() if t.strip()]
        if not terms:
            return query

        # Apply where_any_columns for each term
        for term in terms:
            query = query.where_any_columns(searchable_fields, "LIKE", f"%{term}%")

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
