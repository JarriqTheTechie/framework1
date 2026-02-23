import pprint
import importlib
import importlib.util
import sys
import json
from framework1.database.QueryBuilder import QueryBuilder
from framework1.database.active_record.utils.ModelCollection import ModelCollection
from framework1.dsl.FormDSL.SelectField import SelectField
from framework1.dsl.FormDSL.TextField import TextField
from typing import List
from framework1.dsl.FormDSL.TextField import TextField
from framework1.dsl.FormDSL.BaseField import BaseField, RawField
from framework1.dsl.FormDSL.FieldGroup import FieldGroup
from framework1.dsl.FormDSL.Form import Form
from typing import Tuple
from framework1.database.ActiveRecord import ActiveRecord
from framework1.dsl.InformationSchema import InformationSchema
from framework1.core_services.Request import Request
from framework1.cli.resource_handler import transform_word


def parse_connection_string(conn_str: str) -> dict:
    # Remove trailing semicolons and split by semicolon
    parts = [p.strip() for p in conn_str.strip().strip(';').split(';') if p.strip()]

    parsed = {}
    for part in parts:
        # Each part should be key=value
        if '=' in part:
            key, value = part.split('=', 1)  # Split only on first '='
            parsed[key.strip()] = value.strip()

    return parsed


class F1TableFilterForm(Form):
    def __init__(self, data):
        resource = Request().path().split("/")[-1]

        resource = transform_word(resource)
        resource = transform_word(resource["pascal_plural"])
        title_singular = resource["title_singular"]
        title_plural = resource["title_plural"]
        slug_singular = resource["slug_singular"]
        slug_plural = resource["slug_plural"]
        pascal_singular = resource["pascal_singular"]
        pascal_plural = resource["pascal_plural"]
        snake_singular = resource["snake_singular"]
        snake_plural = resource["snake_plural"]

        super().__init__(data)

    def set_resource_from_table(self, table):
        self.table = table.__class__
        self.model = table.__class__.model
        self.db_table = table.__class__.model.__table__
        self.database = table.__class__.model.__database__
        self.filter_field_meta = getattr(table.__class__, "filter_field_meta", {}) or {}
        self.filter_presets = getattr(table.__class__, "filter_presets", {}) or {}
        try:
            self.database_schema = table.__class__.model.__database__.connection_dict['database']
        except KeyError:
            self.database_schema = parse_connection_string(table.__class__.model.__database__.connection_string).get(
                'DATABASE')

        information_schema = InformationSchema
        information_schema.__driver__ = self.model.__driver__
        information_schema.__database__ = self.database
        self.information_schema = information_schema()
        self.information_schema.remove_ordering()

        self.set_submit_button_class("btn btn-dark mt-3 d-none").set_submit_button_style(
            "border-radius: 0 !important;").set_class("filterForm").set_method("GET")
        return self

    def validate_and_create(self) -> Tuple[None | ActiveRecord, Form]:
        '''
        Validates the form data and creates a new Payment record if valid.
        :return: Tuple containing the created resource or None, and the form instance.
        '''
        if self.validate():
            resource = Payment().create(**self.data)
            return resource, self
        return None, self

    def validate_and_update(self, id: str | int) -> Tuple[None | ActiveRecord, Form]:
        '''
        Validates the form data and updates an existing Payment record if valid.
        :return: Tuple containing the updated resource or None, and the form instance.
        '''
        if self.validate():
            resource = Payment().find(id).update(**self.data)
            return resource, self
        return None, self

    def _infer_type(self, column_name: str, raw_type: str) -> str:
        raw = raw_type.lower()
        if any(tok in raw for tok in ["int", "decimal", "numeric", "float", "double", "real"]):
            return "number"
        if any(tok in raw for tok in ["date", "time"]):
            return "date"
        return "string"

    def schema(self) -> List[BaseField | FieldGroup]:
        if self.information_schema.__driver__ == "mysql":
            table_name = self.db_table.replace(f"{self.database_schema}.", "")
            table_columns = self.information_schema.select("COLUMN_NAME").where("TABLE_NAME", table_name).where(
                "TABLE_SCHEMA",
                self.database_schema).order_by(
                "COLUMN_NAME").all()
        else:
            table_columns = self.information_schema.select("COLUMN_NAME").table(
                f"[{self.database_schema}].INFORMATION_SCHEMA.COLUMNS").where("TABLE_NAME", self.db_table).where(
                "TABLE_SCHEMA", "dbo").order_by("ORDINAL_POSITION").all()

        table_columns_ = []
        option_label_map = {}
        option_type_map = {}

        for column in table_columns:
            for user_defined_filter_field in self.table.filterable_fields:
                if column.COLUMN_NAME == user_defined_filter_field.split(".")[-1]:
                    meta = self.filter_field_meta.get(user_defined_filter_field, {})
                    label = meta.get("label", user_defined_filter_field.replace("_", " ").title())
                    inferred_type = meta.get(
                        "type",
                        self._infer_type(column.COLUMN_NAME, getattr(column, "DATA_TYPE", str(column)))
                    )
                    table_columns_.append(user_defined_filter_field)
                    option_label_map[user_defined_filter_field] = label
                    option_type_map[user_defined_filter_field] = inferred_type

        # Fallback: accept meta-defined fields not present in information schema
        for user_defined_filter_field, meta in self.filter_field_meta.items():
            if user_defined_filter_field not in table_columns_:
                table_columns_.append(user_defined_filter_field)
                option_label_map[user_defined_filter_field] = meta.get(
                    "label", user_defined_filter_field.replace("_", " ").title())
                option_type_map[user_defined_filter_field] = meta.get("type", "string")

        # Build operator options list once; JS will prune per field type
        operator_options = [
            ("where", "Equals"),
            ("not_equal", "Not Equals"),
            ("contains", "Contains"),
            ("starts_with", "Starts With"),
            ("ends_with", "Ends With"),
            ("greater_than", "Greater Than"),
            ("less_than", "Less Than"),
            ("greater_than_eq", "Greater Than or Equal"),
            ("less_than_eq", "Less Than or Equal"),
            ("in", "In List"),
            ("not_in", "Not In List"),
            ("between", "Between"),
            ("is_null", "Is Null"),
            ("is_not_null", "Is Not Null"),
        ]

        presets_json = json.dumps(self.filter_presets)
        field_meta_json = json.dumps(option_type_map)
        return [
            RawField("").default(
                """
                <div class="d-flex align-items-center justify-content-between mb-2">
                    <div class="fw-bold">Filter Presets</div>
                    <div class="d-flex gap-2 align-items-center">
                        <select id="presetSelector" class="form-select form-select-sm w-auto">
                            <option value="">Select preset…</option>
                        </select>
                        <button type="button" class="btn btn-outline-secondary btn-sm" id="clearFiltersBtn">
                            Clear
                        </button>
                    </div>
                </div>
                """
            ),
            RawField("").default(
                f'<input type="hidden" id="filterFieldMeta" value=\'{field_meta_json}\'>'
            ),
            RawField("").default(
                f'<input type="hidden" id="filterPresets" value=\'{presets_json}\'>'
            ),
            FieldGroup(
                f"",
                fields=[
                    SelectField("group[]").set_label("Group #").set_options(
                        [f"Group {n}" for n in range(1, 10)]).set_class(
                        "form-select form-select-sm w-auto"),
                    SelectField("boolean[]").set_label("Boolean").set_options(["AND", "OR"]).set_class(
                        "form-select form-select-sm w-auto"),
                    SelectField(f"field[]").set_label("Field Name").set_class(
                        "form-select form-select-sm").set_options([
                        (column, option_label_map.get(column, column))
                        for column in table_columns_
                    ]),

                    SelectField(f"operator[]").set_label("Operator").set_class(
                        "form-select form-select-sm w-auto").set_options(operator_options),
                    RawField(f"value_wrapper").default(
                        '<input name="value[]" type="text" class="form-control form-control-sm" />'
                    ),
                    RawField("").default(
                        '<i class="ri-close-circle-line remove-btn" onclick="removeFilterRow(this)"></i>')
                ]

            ).set_field_container_class("").set_title_class("h6 fw-bold ps-0")
            .set_class("col-12 filter-row d-flex align-items-center gap-2").wrap_in_div_with_class_and_id("filterRows",
                                                                                                          "filterRows"),
            FieldGroup(
                "",
                fields=[
                    RawField("").default(f"""
                        <!-- Add Filter Button -->
                        <button type="button" class="btn btn-outline-primary btn-sm mt-2" onclick="addFilterRow()">
                            <i class="ri-add-line me-1"></i> Add Condition
                        </button>

                        <!-- Action Buttons -->
                        <div class="filter-actions mt-4 d-flex justify-content-between">
                            <button type="reset" class="btn btn-outline-secondary btn-sm">
                                <i class="ri-refresh-line me-1"></i> Reset
                            </button>
                            <button type="submit" class="btn btn-primary btn-sm">
                                <i class="ri-search-line me-1"></i> Apply
                            </button>
                        </div>
                    """)
                ]
            )
        ]
