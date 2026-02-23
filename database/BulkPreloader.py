from framework1.database.QueryBuilder import QueryBuilder, count_sql_placeholders
from framework1.database.schema_cache import get_table_columns_cached
from copy import deepcopy
import re
import hashlib


def get_relationship_type(fn) -> str:
    if getattr(fn, "__has_one_through__", False):
        return "through"
    if getattr(fn, "__has_one__", False) or getattr(fn, "__belongs_to__", False):
        return "one"
    return "many"


class BulkPreloader:
    def __init__(self, models: "ModelCollection", instance=None):
        from framework1.database.active_record.utils.ModelCollection import ModelCollection

        self.models = models
        self.instance = instance
        self.primary_model = models[0] if models else None
        self.withs = self._resolve_withs()

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------
    def run(self):
        from framework1.database.active_record.utils.ModelCollection import ModelCollection

        if not self.models or not self.withs:
            return

        current_level = [{
            "models": list(self.models),
            "withs": list(self.withs),
            "instance": self.instance,
        }]

        while current_level:
            coalesced_level = self._coalesce_level_batches(current_level)
            next_level = []

            for batch in coalesced_level:
                models = batch["models"]
                withs = batch["withs"]
                instance = batch["instance"]
                if not models or not withs:
                    continue

                current = BulkPreloader(ModelCollection(models), instance=instance)
                current.withs = withs

                queries, join_meta = current._build_queries()
                if not queries:
                    continue

                raw_results = current._execute_pqueries(queries)
                rel_results = current._normalize_results(raw_results)
                nested_batches = current._assign_results(rel_results, join_meta)

                for nested in nested_batches:
                    next_level.append({
                        "models": nested["models"],
                        "withs": nested["withs"],
                        "instance": None,
                    })

            current_level = next_level

    @staticmethod
    def _coalesce_level_batches(level_batches: list[dict]) -> list[dict]:
        """
        BFS batching optimization:
        merge same-depth batches that target the same model class and with-signature.
        """
        grouped = {}
        for batch in level_batches:
            models = batch.get("models") or []
            withs = batch.get("withs") or []
            instance = batch.get("instance")
            if not models or not withs:
                continue

            model_cls = models[0].__class__
            key = (model_cls, tuple(withs))
            target = grouped.get(key)
            if target is None:
                grouped[key] = {
                    "models": list(models),
                    "withs": list(withs),
                    "instance": instance,
                }
            else:
                target["models"].extend(models)

        coalesced = []
        for value in grouped.values():
            seen = set()
            unique_models = []
            for m in value["models"]:
                marker = id(m)
                if marker in seen:
                    continue
                seen.add(marker)
                unique_models.append(m)
            value["models"] = unique_models
            coalesced.append(value)

        return coalesced

    # ---------------------------------------------------------
    # WITH resolution
    # ---------------------------------------------------------
    def _resolve_withs(self):
        target = self.instance if self.instance is not None else self.primary_model
        if not target:
            return []

        if getattr(target, "_with_overrides", None) is not None:
            return target._with_overrides

        return getattr(target, "__with__", [])

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    @staticmethod
    def _field_from_key(key: str) -> str:
        return key.split(".")[-1] if "." in key else key

    @staticmethod
    def _chunk_list(values: list, size: int) -> list[list]:
        if size <= 0:
            size = 500
        return [values[i:i + size] for i in range(0, len(values), size)]

    @staticmethod
    def _loosely_typed_match(left, right) -> bool:
        """
        Match values while preserving prior type-coercion behavior, but safely handle None.
        """
        if left is None or right is None:
            return left == right
        try:
            return type(left)(right) == left
        except Exception:
            return right == left

    @staticmethod
    def _parse_preload_hint(rel_query) -> dict:
        raw = getattr(rel_query, "__preload_hint__", None)
        if isinstance(raw, str):
            return {"strategy": raw.strip().lower() or "in"}
        if isinstance(raw, dict):
            strategy = str(raw.get("strategy", "in")).strip().lower() or "in"
            hint = dict(raw)
            hint["strategy"] = strategy
            return hint
        return {"strategy": "in"}

    # ---------------------------------------------------------
    # Query builders
    # ---------------------------------------------------------
    def _build_many_query(self, rel_query, fk_field, owner_field):
        constraints = getattr(rel_query, "__constraints__", None)
        if constraints:
            if isinstance(constraints, QueryBuilder):
                return constraints
            else:
                raise TypeError(
                    "__constraints__ must return a QueryBuilder"
                )

        ids = [
            m.__data__.get(self._field_from_key(owner_field))
            for m in self.models
            if m.__data__.get(self._field_from_key(owner_field)) is not None
        ]

        if not ids:
            ids = [self.models[0].__data__.get(fk_field)]

        return BulkPreloader.remove_first_condition(rel_query).where_in(fk_field, ids)

    def _build_one_or_belongs_to_query(self, rel_query, fk_field, owner_field):
        fk_key = self._field_from_key(fk_field)
        parent_fk_values = [
            m.__data__.get(fk_key)
            for m in self.models
            if m.__data__.get(fk_key) is not None
        ]

        if not parent_fk_values:
            return BulkPreloader.remove_first_condition(rel_query).where_raw("1 = 0")

        return (
            BulkPreloader.remove_first_condition(rel_query)
            .where_in(owner_field, parent_fk_values)
        )

    def _build_through_query(self, rel_query):
        through_model = rel_query.__through__
        through_owner_key = rel_query.__through_owner_key__
        second_key = rel_query.__second_key__
        target_owner_key = rel_query.__target_owner_key__

        fk_values = [getattr(m, rel_query.__first_key__) for m in self.models]
        through_records = through_model().where_in(
            through_owner_key, fk_values
        ).all()

        target_ids = [
            getattr(tr, second_key)
            for tr in through_records
            if getattr(tr, second_key)
        ]

        return rel_query.where_in(target_owner_key, target_ids), target_owner_key

    # ---------------------------------------------------------
    # Query construction
    # ---------------------------------------------------------
    @staticmethod
    def parse_withs(withs: list[str]) -> dict:
        """
        Turns ["client.alerts", "client.profile", "user.roles.permissions"]
        into:
        {
            "client": {"alerts": {}, "profile": {}},
            "user": {"roles": {"permissions": {}}}
        }
        """
        tree = {}
        for w in withs:
            parts = w.split(".")
            node = tree
            for p in parts:
                node = node.setdefault(p, {})
        return tree

    @staticmethod
    def remove_first_condition(query_obj: QueryBuilder, clone: bool = True) -> QueryBuilder:
        """
        Safely remove the first WHERE condition and its bound parameter.

        Args:
            query_obj: The query builder or ActiveRecord instance.
            clone: If True, returns a cloned copy; if False, mutates in place.

        Returns:
            QueryBuilder with first condition + parameter removed.
        """
        if clone:
            try:
                target = query_obj.clone()
            except Exception:
                target = deepcopy(query_obj)
        else:
            target = query_obj

        if getattr(target, "conditions", None):
            target.conditions = target.conditions[1:]

        if getattr(target, "parameters", None):
            target.parameters = target.parameters[1:]

        # Guard against dangling params after condition stripping (e.g., relation
        # builders carrying stale limit/order bindings on clone variants).
        original_scopes_enabled = None
        try:
            # Avoid side effects from to_sql() scope application while counting.
            original_scopes_enabled = getattr(target, "__scopes_enabled__", None)
            if original_scopes_enabled is not None:
                target.__scopes_enabled__ = False
            placeholder_count = count_sql_placeholders(target.to_sql())
            if len(getattr(target, "parameters", []) or []) > placeholder_count:
                target.parameters = target.parameters[:placeholder_count]
        except Exception:
            pass
        finally:
            if original_scopes_enabled is not None:
                target.__scopes_enabled__ = original_scopes_enabled

        return target

    def _build_queries(self):
        queries = []
        join_meta = []

        with_tree = self.parse_withs(self.withs)

        for relationship, nested in with_tree.items():
            rel_query = getattr(self.primary_model, relationship)()
            database = rel_query.db
            rel_cls = rel_query.__class__

            rel_type = get_relationship_type(rel_query)

            fk_field = getattr(rel_query, "__foreign_key__", None)
            owner_field = getattr(rel_query, "__owner_key__", None)
            fk_alias = getattr(rel_query, "__foreign_key_alias__", None)
            owner_alias = getattr(rel_query, "__owner_key_alias__", None)
            match_fn = getattr(rel_query, "__match_fn__", None)
            constraints = getattr(rel_query, "__constraints__", None)
            hint = self._parse_preload_hint(rel_query)
            strategy = hint.get("strategy", "in")

            if strategy == "skip":
                join_meta.append({
                    "rel": relationship,
                    "rel_type": rel_type,
                    "rel_cls": rel_cls,
                    "fk_field": fk_field,
                    "foreign_key_alias": fk_alias,
                    "owner_key": owner_field,
                    "owner_key_alias": owner_alias,
                    "nested_withs": {},
                    "match_fn": match_fn,
                    "constraints": constraints,
                    "preload_strategy": strategy,
                    "exists_only": False,
                })
                continue

            if not match_fn and not constraints:
                if not fk_field or not owner_field:
                    raise Exception(
                        f"Relationship '{relationship}' did not define foreign_key/owner_key properly"
                    )

            if rel_type == "many":
                bulk_query = self._build_many_query(rel_query, fk_field, owner_field)

            elif rel_type == "through":
                bulk_query, fk_field = self._build_through_query(rel_query)
                owner_field = None

            else:
                bulk_query = self._build_one_or_belongs_to_query(
                    rel_query, fk_field, owner_field
                )

            exists_only = strategy == "exists_only" and rel_type in ("many", "one")
            if exists_only:
                match_col = fk_alias or fk_field if rel_type == "many" else owner_field
                if match_col:
                    bulk_query.select([self._qualify_with_base_table(bulk_query, self._field_from_key(match_col))])

            if strategy == "chunked_in" and rel_type in ("many", "one") and not match_fn and not constraints:
                chunk_size = int(hint.get("chunk", 500) or 500)
                if rel_type == "many":
                    id_values = [
                        m.__data__.get(self._field_from_key(owner_field))
                        for m in self.models
                        if m.__data__.get(self._field_from_key(owner_field)) is not None
                    ]
                else:
                    id_values = [
                        m.__data__.get(self._field_from_key(fk_field))
                        for m in self.models
                        if m.__data__.get(self._field_from_key(fk_field)) is not None
                    ]
                # Stable de-dup for smaller SQL/params
                deduped_ids = []
                seen_ids = set()
                for value in id_values:
                    marker = str(value)
                    if marker in seen_ids:
                        continue
                    seen_ids.add(marker)
                    deduped_ids.append(value)

                if not deduped_ids:
                    bulk_chunks = [bulk_query]
                else:
                    bulk_chunks = []
                    for id_chunk in self._chunk_list(deduped_ids, chunk_size):
                        q = BulkPreloader.remove_first_condition(rel_query).where_in(
                            fk_field if rel_type == "many" else owner_field,
                            id_chunk,
                        )
                        if exists_only:
                            match_col = fk_alias or fk_field if rel_type == "many" else owner_field
                            if match_col:
                                q.select([self._qualify_with_base_table(q, self._field_from_key(match_col))])
                        bulk_chunks.append(q)
            else:
                bulk_chunks = [bulk_query]

            # Memory guard: avoid SELECT * for standard preload paths when safe.
            # Keep custom/constraint/match_fn queries and joined queries untouched.
            if (
                not match_fn
                and not constraints
                and getattr(rel_cls, "__optimize_preloader_projection__", False)
            ):
                bulk_query = self._optimize_projection_for_preload(
                    bulk_query,
                    rel_cls,
                    fk_field=fk_field,
                    owner_field=owner_field,
                    fk_alias=fk_alias,
                    owner_alias=owner_alias,
                )

            for bq in bulk_chunks:
                queries.append({
                    relationship: bq.to_sql(),
                    "db": database.__class__.__name__,
                    "params": bq.parameters,
                    "db_instance": database
                })

            join_meta.append({
                "rel": relationship,
                "rel_type": rel_type,
                "rel_cls": rel_cls,
                "fk_field": fk_field,
                "foreign_key_alias": fk_alias,
                "owner_key": owner_field,
                "owner_key_alias": owner_alias,
                "nested_withs": nested,
                "match_fn": match_fn,
                "constraints": constraints,
                "preload_strategy": strategy,
                "exists_only": exists_only,
            })

        return queries, join_meta

    def _optimize_projection_for_preload(
        self,
        query: QueryBuilder,
        rel_cls,
        fk_field: str | None,
        owner_field: str | None,
        fk_alias: str | None,
        owner_alias: str | None,
    ) -> QueryBuilder:
        # Materialize scope effects first so joins/select clauses reflect final SQL shape.
        if getattr(query, "__scopes_enabled__", False) and hasattr(query, "apply_scopes"):
            try:
                query.apply_scopes()
                query.__scopes_enabled__ = False
            except Exception:
                return query

        columns = getattr(query, "columns", None) or []
        if not (len(columns) == 1 and str(columns[0]).strip() == "*"):
            return query

        # Joined relationship queries often need custom projection semantics.
        if getattr(query, "joins", None):
            return query

        db_columns = self._get_db_table_columns(query)
        if not db_columns:
            return query
        db_columns_set = set(db_columns)

        try:
            base_fields = [f for f in rel_cls.get_fields().keys() if f in db_columns_set]
        except Exception:
            base_fields = []

        include = getattr(rel_cls, "__projection_include__", None)
        exclude = set(getattr(rel_cls, "__projection_exclude__", []) or [])
        if include:
            include_set = set(include)
            base_fields = [f for f in base_fields if f in include_set]
        if exclude:
            base_fields = [f for f in base_fields if f not in exclude]

        extra_keys = []
        for key in (fk_field, owner_field, fk_alias, owner_alias):
            if key:
                leaf = self._field_from_key(key)
                if leaf in db_columns_set:
                    extra_keys.append(leaf)

        # Relationship matching requires the foreign key to be present in hydrated rows.
        required_fk_leaf = self._field_from_key(fk_alias or fk_field) if (fk_alias or fk_field) else None
        if required_fk_leaf and required_fk_leaf not in db_columns_set:
            return query

        select_cols = []
        seen = set()
        for col in base_fields + extra_keys:
            if not col or col in seen:
                continue
            seen.add(col)
            select_cols.append(col)

        if select_cols:
            query.select([self._qualify_with_base_table(query, c) for c in select_cols])
        return query

    def _qualify_with_base_table(self, query: QueryBuilder, column: str) -> str:
        col = str(column).strip()
        if not col or "." in col:
            return col
        table_name = str(getattr(query, "__table__", "") or "").strip()
        # If table has alias/subquery syntax, fall back to raw column name.
        if not table_name or " " in table_name or "(" in table_name or ")" in table_name:
            return col
        return f"{table_name}.{col}"

    def _get_db_table_columns(self, query: QueryBuilder):
        return get_table_columns_cached(
            db=getattr(query, "db", None),
            driver=getattr(query, "__driver__", ""),
            table_raw=getattr(query, "__table__", ""),
        )

    # ---------------------------------------------------------
    # Parallel execution
    # ---------------------------------------------------------
    def _execute_pqueries(self, queries):
        from framework1.database.active_record.utils.ModelCollection import ModelCollection

        results = []
        databases = ModelCollection(list({q["db"] for q in queries}))
        queries = ModelCollection(queries)
        request_cache = self._get_request_relation_cache()

        for db in databases:
            group = queries.where(lambda q: q["db"] == db)
            db_instance = group.first()["db_instance"]

            # Preserve original relationship-key order while deduping identical SQL+params.
            original_entries = []
            unique_map = {}  # (sql, params_tuple) -> synthetic key
            unique_qset = []
            unique_params = []
            unique_pending_sigs = []
            rows_by_sig = {}

            for item in group:
                rel_key = next(k for k in item.keys() if k not in ("db", "params", "db_instance"))
                sql = item[rel_key]
                params_tuple = tuple(item.get("params") or [])
                sig = (sql, params_tuple)
                original_entries.append((rel_key, sig))

                if sig in unique_map:
                    continue

                cache_key = self._relation_cache_key(db, sql, params_tuple)
                cached_rows = request_cache.get(cache_key)
                if cached_rows is not None:
                    rows_by_sig[sig] = list(cached_rows)
                    continue

                synthetic_key = f"q{len(unique_map)}"
                unique_map[sig] = synthetic_key
                unique_qset.append({synthetic_key: sql})
                if params_tuple:
                    unique_params.extend(params_tuple)
                unique_pending_sigs.append(sig)

            raw_unique_results = db_instance.pquery(unique_qset, *unique_params) if unique_qset else []
            rows_by_synthetic_key = {}
            for item in raw_unique_results:
                for key, rows in item.items():
                    rows_by_synthetic_key[key] = rows

            for sig in unique_pending_sigs:
                skey = unique_map.get(sig)
                rows = list(rows_by_synthetic_key.get(skey, []))
                rows_by_sig[sig] = rows
                cache_key = self._relation_cache_key(db, sig[0], sig[1])
                request_cache[cache_key] = list(rows)

            # Rehydrate to expected shape: [{relationship_name: rows}, ...]
            for rel_key, sig in original_entries:
                rows = rows_by_sig.get(sig)
                if rows is None:
                    skey = unique_map.get(sig)
                    rows = rows_by_synthetic_key.get(skey, [])
                results.append({rel_key: list(rows)})

        return results

    def _relation_cache_key(self, db_name: str, sql: str, params_tuple: tuple):
        payload = f"{db_name}|{sql}|{repr(params_tuple)}".encode("utf-8")
        return hashlib.sha1(payload).hexdigest()

    def _get_request_relation_cache(self) -> dict:
        try:
            from flask import g, has_app_context
            if has_app_context():
                cache = getattr(g, "_bulk_preload_relation_cache", None)
                if cache is None:
                    cache = {}
                    g._bulk_preload_relation_cache = cache
                return cache
        except Exception:
            pass
        # Fallback (non-request context): per-preloader instance cache
        cache = getattr(self, "_local_relation_cache", None)
        if cache is None:
            cache = {}
            self._local_relation_cache = cache
        return cache

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------
    @staticmethod
    def _normalize_results(pquery_results):
        rel_results = {}
        for res in pquery_results:
            for key, rows in res.items():
                rel_results.setdefault(key, []).extend([dict(r) for r in rows])
        return rel_results

    # ---------------------------------------------------------
    # Hydration + assignment
    # ---------------------------------------------------------
    def _assign_results(self, rel_results, join_meta):
        nested_many_batches = {}
        nested_single_batches = {}
        through_lookup_cache = {}

        for model in self.models:
            for meta_idx, meta in enumerate(join_meta):
                rel = meta["rel"]
                rel_type = meta["rel_type"]
                rel_cls = meta["rel_cls"]
                fk = meta["fk_field"]
                fk_alias = meta["foreign_key_alias"]
                owner = meta["owner_key"]
                nested = meta["nested_withs"]
                match_fn = meta["match_fn"]
                constraints = meta["constraints"]
                preload_strategy = meta.get("preload_strategy", "in")
                exists_only = bool(meta.get("exists_only", False))

                if preload_strategy == "skip":
                    setattr(model, f"_{rel}_cache", None if rel_type == "one" else [])
                    continue

                if rel not in rel_results or not rel_cls:
                    setattr(model, f"_{rel}_cache", None if rel_type == "one" else [])
                    continue

                raw_rows = rel_results[rel]

                if exists_only:
                    if rel_type == "many":
                        owner_value = model.__data__.get(self._field_from_key(owner))
                        key_name = self._field_from_key(fk_alias or fk)
                    else:
                        owner_value = model.__data__.get(self._field_from_key(fk))
                        key_name = self._field_from_key(owner)

                    found = False
                    owner_marker = str(owner_value) if owner_value is not None else None
                    if owner_marker is not None:
                        for row in raw_rows:
                            row_value = row.get(key_name)
                            if row_value is None:
                                continue
                            if str(row_value) == owner_marker or self._loosely_typed_match(owner_value, row_value):
                                found = True
                                break

                    model.__data__[f"{rel}_exists"] = 1 if found else 0
                    setattr(model, f"_{rel}_cache", None if rel_type == "one" else [])
                    continue

                hydrated = (
                    rel_cls()._hydrate_results(raw_rows)
                    if not match_fn and not constraints
                    else raw_rows
                )

                if rel_type == "many":
                    pk = model.__data__.get(self._field_from_key(owner))

                    related = (
                        match_fn(hydrated)
                        if match_fn
                        else [
                            r for r in hydrated
                            if self._loosely_typed_match(pk, r.__data__.get(fk_alias or fk))
                        ]
                    )

                    setattr(model, f"_{rel}_cache", related)

                    if nested and related:
                        batch_key = (meta_idx, rel)
                        batch = nested_many_batches.get(batch_key)
                        if batch is None:
                            batch = {
                                "withs": [
                                    f"{k}" if not v else f"{k}.{'.'.join(v.keys())}"
                                    for k, v in nested.items()
                                ],
                                "related": [],
                            }
                            nested_many_batches[batch_key] = batch
                        batch["related"].extend(related)


                elif rel_type == "through":
                    through_model = getattr(model, rel)().__through__
                    through_owner_key = getattr(model, rel)().__through_owner_key__
                    first_key = getattr(model, rel)().__first_key__
                    second_key = getattr(model, rel)().__second_key__
                    target_owner_key = getattr(model, rel)().__target_owner_key__

                    lookup_key = (meta_idx, rel, through_owner_key, first_key)
                    through_lookup = through_lookup_cache.get(lookup_key)
                    if through_lookup is None:
                        through_lookup = {
                            getattr(tr, through_owner_key): tr
                            for tr in through_model().where_in(
                                through_owner_key,
                                [getattr(m, first_key) for m in self.models]
                            ).all()
                        }
                        through_lookup_cache[lookup_key] = through_lookup

                    related = None
                    through_value = through_lookup.get(getattr(model, first_key))

                    if through_value:
                        target_key = getattr(through_value, second_key)
                        related = next(
                            (
                                r for r in hydrated
                                if self._loosely_typed_match(target_key, getattr(r, target_owner_key))
                            ),
                            None
                        )
                    setattr(model, f"_{rel}_cache", related)

                    if nested and related:
                        batch_key = (meta_idx, rel)
                        batch = nested_single_batches.get(batch_key)
                        if batch is None:
                            batch = {
                                "withs": [
                                    f"{k}" if not v else f"{k}.{'.'.join(v.keys())}"
                                    for k, v in nested.items()
                                ],
                                "related": [],
                            }
                            nested_single_batches[batch_key] = batch
                        batch["related"].append(related)
                else:  # one / belongs_to
                    parent_fk = model.__data__.get(self._field_from_key(fk))
                    if parent_fk is not None:
                        related = next(
                            (
                                r for r in hydrated
                                if self._loosely_typed_match(parent_fk, r.__data__.get(self._field_from_key(owner)))
                            ),
                            None
                        )
                        setattr(model, f"_{rel}_cache", related)

                        if nested and related:
                            batch_key = (meta_idx, rel)
                            batch = nested_single_batches.get(batch_key)
                            if batch is None:
                                batch = {
                                    "withs": [
                                        f"{k}" if not v else f"{k}.{'.'.join(v.keys())}"
                                        for k, v in nested.items()
                                    ],
                                    "related": [],
                            }
                                nested_single_batches[batch_key] = batch
                            batch["related"].append(related)

        nested_batches = []
        # Prepare nested "many" relationship batches.
        for batch in nested_many_batches.values():
            unique_related = []
            seen = set()
            for related in batch["related"]:
                marker = id(related)
                if marker in seen:
                    continue
                seen.add(marker)
                related.__with__ = batch["withs"]
                unique_related.append(related)

            if unique_related:
                nested_batches.append({
                    "models": unique_related,
                    "withs": batch["withs"]
                })

        # Prepare nested single-object relationship batches.
        for batch in nested_single_batches.values():
            unique_related = []
            seen = set()
            for related in batch["related"]:
                marker = id(related)
                if marker in seen:
                    continue
                seen.add(marker)
                related.__with__ = batch["withs"]
                unique_related.append(related)

            if unique_related:
                nested_batches.append({
                    "models": unique_related,
                    "withs": batch["withs"]
                })

        return nested_batches

    def _explain_node(self, model, tree: dict) -> dict:
        plan = {}

        for rel_name, nested in tree.items():
            rel_query = getattr(model, rel_name)()
            rel_type = get_relationship_type(rel_query)

            plan[rel_name] = {
                "type": rel_type,
                "with": self._explain_node(
                    rel_query.__class__(),
                    nested
                ) if nested else {}
            }

        return plan

    def explain(self) -> dict:
        """
        Returns a structured preload execution plan including
        relationship types and nesting.
        """
        if not self.withs or not self.primary_model:
            return {}

        with_tree = BulkPreloader.parse_withs(self.withs)
        return self._explain_node(self.primary_model, with_tree)
