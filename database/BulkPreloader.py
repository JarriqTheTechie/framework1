from framework1.database.QueryBuilder import QueryBuilder
from copy import deepcopy


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
        if not self.models or not self.withs:
            return

        queries, join_meta = self._build_queries()
        if not queries:
            return

        raw_results = self._execute_pqueries(queries)
        rel_results = self._normalize_results(raw_results)
        self._assign_results(rel_results, join_meta)

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
            if m.__data__.get(self._field_from_key(owner_field))
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
        target = deepcopy(query_obj) if clone else query_obj

        if getattr(target, "conditions", None):
            target.conditions = target.conditions[1:]

        if getattr(target, "parameters", None):
            target.parameters = target.parameters[1:]

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

            if not getattr(rel_query, "__match_fn__", None) and not getattr(rel_query, "__constraints__", None):
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

            queries.append({
                relationship: bulk_query.to_sql(),
                "db": database.__class__.__name__,
                "params": bulk_query.parameters,
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
                "match_fn": getattr(rel_query, "__match_fn__", None),
                "constraints": getattr(rel_query, "__constraints__", None)
            })

        return queries, join_meta

    # ---------------------------------------------------------
    # Parallel execution
    # ---------------------------------------------------------
    def _execute_pqueries(self, queries):
        from framework1.database.active_record.utils.ModelCollection import ModelCollection

        results = []
        databases = ModelCollection(list({q["db"] for q in queries}))
        queries = ModelCollection(queries)

        for db in databases:
            db_instance = queries.where(
                lambda q: q["db"] == db
            ).first()["db_instance"]

            qset = []
            params = []

            for q in queries.where(lambda q: q["db"] == db):
                q = deepcopy(q)
                p = q.pop("params")
                q.pop("db")
                q.pop("db_instance")
                if p:
                    params.extend(p)
                qset.append(q)

            results.extend(db_instance.pquery(qset, *params))

        return results

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------
    @staticmethod
    def _normalize_results(pquery_results):
        rel_results = {}
        for res in pquery_results:
            for key, rows in res.items():
                rel_results[key] = [dict(r) for r in rows]
        return rel_results

    # ---------------------------------------------------------
    # Hydration + assignment
    # ---------------------------------------------------------
    def _assign_results(self, rel_results, join_meta):
        from framework1.database.active_record.utils.ModelCollection import ModelCollection

        for model in self.models:
            for meta in join_meta:
                rel = meta["rel"]
                rel_type = meta["rel_type"]
                rel_cls = meta["rel_cls"]
                fk = meta["fk_field"]
                fk_alias = meta["foreign_key_alias"]
                owner = meta["owner_key"]
                nested = meta["nested_withs"]
                match_fn = meta["match_fn"]
                constraints = meta["constraints"]

                if rel not in rel_results or not rel_cls:
                    setattr(model, f"_{rel}_cache", None if rel_type == "one" else [])
                    continue

                raw_rows = rel_results[rel]
                hydrated = (
                    rel_cls()._hydrate_results(raw_rows)
                    if not match_fn and not constraints
                    else raw_rows
                )

                if rel_type == "many":
                    pk = model.__data__.get(self._field_from_key(owner))
                    pk_type = type(pk)

                    related = (
                        match_fn(hydrated)
                        if match_fn
                        else [
                            r for r in hydrated
                            if pk_type(r.__data__.get(fk_alias or fk)) == pk
                        ]
                    )

                    setattr(model, f"_{rel}_cache", related)

                    if nested and related:
                        for r in related:
                            r.__with__ = [
                                f"{k}" if not v else f"{k}.{'.'.join(v.keys())}"
                                for k, v in nested.items()
                            ]
                        BulkPreloader(ModelCollection(related)).run()


                elif rel_type == "through":
                    through_model = getattr(model, rel)().__through__
                    through_owner_key = getattr(model, rel)().__through_owner_key__
                    first_key = getattr(model, rel)().__first_key__
                    second_key = getattr(model, rel)().__second_key__
                    target_owner_key = getattr(model, rel)().__target_owner_key__

                    through_lookup = {
                        getattr(tr, through_owner_key): tr
                        for tr in through_model().where_in(
                            through_owner_key,
                            [getattr(m, first_key) for m in self.models]
                        ).all()
                    }

                    related = None
                    through_value = through_lookup.get(getattr(model, first_key))

                    if through_value:
                        target_key = getattr(through_value, second_key)
                        target_key_type = type(target_key)
                        related = next(
                            (
                                r for r in hydrated
                                if target_key_type(getattr(r, target_owner_key)) == target_key
                            ),
                            None
                        )
                    setattr(model, f"_{rel}_cache", related)

                    if nested and related:
                        related.__with__ = [
                            f"{k}" if not v else f"{k}.{'.'.join(v.keys())}"
                            for k, v in nested.items()
                        ]
                        BulkPreloader(ModelCollection([related])).run()
                else:  # one / belongs_to
                    parent_fk = model.__data__.get(self._field_from_key(fk))
                    if parent_fk:
                        key_type = type(parent_fk)
                        related = next(
                            (r for r in hydrated if key_type(r.__data__.get(self._field_from_key(owner))) == parent_fk),
                            None
                        )
                        setattr(model, f"_{rel}_cache", related)

                        if nested and related:
                            related.__with__ = [
                                f"{k}" if not v else f"{k}.{'.'.join(v.keys())}"
                                for k, v in nested.items()
                            ]
                            BulkPreloader(ModelCollection([related])).run()

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
