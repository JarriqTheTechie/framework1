from dataclasses import dataclass, asdict, fields, field, is_dataclass
from typing import get_origin

def _is_empty(val):
    return val is None or val == "" or (isinstance(val, (list, dict)) and not val)

@dataclass
class BaseDTO:
    __extras__: dict = field(default_factory=dict, init=False, repr=False)
    _extra_fields: list[str] = field(default_factory=list, init=False, repr=False)
    _errors: dict = field(default_factory=dict, init=False, repr=False)

    def to_dict(
        self,
        exclude: list[str] = None,
        only: list[str] = None,
        include_extras: list[str] = None
    ) -> dict:
        """
        Convert DTO to dict with optional exclusion/inclusion of fields.
        Only exports selected extras.
        """
        data = asdict(self)
        data.pop("__extras__", None)
        data.pop("_extra_fields", None)
        data.pop("_errors", None)

        # choose extras: per-call override > configured extras
        chosen_extras = include_extras if include_extras is not None else self._extra_fields
        for key in chosen_extras:
            if key in self.__extras__:
                data[key] = self.__extras__[key]

        if only:
            data = {k: v for k, v in data.items() if k in only}
        if exclude:
            for field in exclude:
                data.pop(field, None)

        return data

    def ingest_data(
        self,
        list_of_sources: list,
        override_existing: bool = True,
        field_overrides: dict[str, str] = None,
        converters: dict[str, callable] = None,
        mutators: dict[str, callable] = None,
        validators: dict[str, callable] = None,
    ):
        if field_overrides is None:
            field_overrides = {}
        if converters is None:
            converters = {}
        if mutators is None:
            mutators = {}
        if validators is None:
            validators = {}

        # reset errors on every ingest
        self._errors = {}

        field_types = {f.name: f.type for f in fields(self)}

        # --- ingest from sources
        for source in list_of_sources:
            if isinstance(source, BaseDTO):
                source = source.to_dict(include_extras=list(source.__extras__.keys()))
            elif not isinstance(source, dict):
                try:
                    source = dict(source)
                except Exception:
                    continue

            for key, value in source.items():
                target_field = field_overrides.get(key, key)

                if target_field not in field_types:
                    # unknown → stash in extras
                    self.__extras__[target_field] = value
                    continue

                current_val = getattr(self, target_field, None)
                if not override_existing and not _is_empty(current_val):
                    continue

                # explicit converter
                if target_field in converters:
                    try:
                        value = converters[target_field](value)
                    except Exception:
                        pass
                else:
                    anno = field_types.get(target_field)
                    if anno and value is not None:
                        try:
                            origin = get_origin(anno) or anno
                            if is_dataclass(origin) and isinstance(value, dict):
                                nested = getattr(self, target_field, None)
                                if nested is None:
                                    nested = origin()
                                nested.ingest_data([value], override_existing=override_existing)
                                value = nested
                            else:
                                value = origin(value)
                        except Exception:
                            pass

                # mutator on *incoming* value
                if target_field in mutators:
                    try:
                        value = mutators[target_field](value)
                    except Exception:
                        pass

                setattr(self, target_field, value)

        # --- after ingest: run mutators across DTO state
        for f in fields(self):
            name = f.name
            if name in mutators:
                try:
                    current_val = getattr(self, name)
                    new_val = mutators[name](current_val)
                    setattr(self, name, new_val)
                except Exception:
                    pass

        for key, val in list(self.__extras__.items()):
            if key in mutators:
                try:
                    self.__extras__[key] = mutators[key](val)
                except Exception:
                    pass

        # --- run validators, collect errors ---
        for f in fields(self):
            name = f.name
            if name in validators:
                value = getattr(self, name)
                try:
                    validated = validators[name](value, field_name=name)
                    setattr(self, name, validated)
                except Exception as e:
                    self._errors.setdefault(name, []).append(str(e))

        for key, val in list(self.__extras__.items()):
            if key in validators:
                try:
                    self.__extras__[key] = validators[key](val, field_name=key)
                except Exception as e:
                    self._errors.setdefault(key, []).append(str(e))

        return self

    def allow_extras(self, fields: list[str]):
        """Convenience method to configure which extras get exported by default"""
        self._extra_fields = fields
        return self

    def is_valid(self) -> bool:
        """Return True if no validation errors exist"""
        return not bool(self._errors)

    @property
    def errors(self) -> dict:
        """Return validation errors collected during ingest"""
        return self._errors
