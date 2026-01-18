import fnmatch
import os
import re
import secrets
import uuid
from calendar import monthrange
from collections import defaultdict
from dataclasses import fields, is_dataclass, asdict
from datetime import datetime, time as dtime, timezone, timedelta
from secrets import compare_digest
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from flask import request, flash, session, get_flashed_messages
from framework1.core_services.validators import get_rule
from werkzeug.datastructures import FileStorage

COMMON_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%d/%m/%Y"
]

COMMON_DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",  # HTML datetime-local with seconds
    "%Y-%m-%dT%H:%M",  # HTML datetime-local no seconds
    "%d-%m-%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S"
]

COMMON_TIME_FORMATS = [
    "%H:%M:%S",
    "%H:%M",
    "%I:%M %p",  # 12-hour time (e.g., 2:30 PM)
]


def POSTMethod():
    return 'POST'


def GETMethod():
    return 'GET'


class UploadedFile:
    def __init__(self, stream, filename, name, content_type):
        self.file = FileStorage(stream, filename, name, content_type)

    def save(self, path: str = None, prefix: str = "", suffix: str = "", prefix_separator: str = "",
             suffix_separator: str = "",
             keep_name: bool = False, upload_dir=os.getenv("UPLOAD_DIR")):

        if not upload_dir:
            upload_dir = "uploads"

        extension: str = self.extension()
        if keep_name is True:
            path = upload_dir + "/" + self.file.filename
        else:
            path = upload_dir + "/" + f"{prefix}{prefix_separator}{path or str(uuid.uuid4())}{suffix_separator}{suffix}" + "." + extension
            path = path.strip()

        if path:
            self.file.save(path)
        else:
            self.file.save(self.file.filename)

        return path

    def extension(self):
        return self.file.filename.split('.')[-1]

    def path(self):
        return self.file.filename

    def mimetype(self):
        return self.file.content_type

    def size(self, format: str = 'kb'):
        size = len(self.file.read())
        if format == 'kb':
            return round(size / 1024, 2)
        elif format == 'mb':
            return round(size / 1024 / 1024, 2)
        elif format == 'gb':
            return round(size / 1024 / 1024 / 1024, 2)
        return round(size, 2)

    @property
    def filename(self):
        return self.file.filename


class Request:
    def __init__(self):
        self.request.flash = flash
        self.request.session = session

    def __get_json(self):
        if self.request.content_type == 'application/json':
            return self.request.json
        return {}

    def form(self, group: str) -> dict:
        """
        Extract inputs like group[field] as a nested dictionary.
        Example: <input name="billing[address]"> ➜ request.form("billing") ➜ {"address": "123 Main St"}
        """
        result = {}
        prefix = f"{group}["
        for key, value in self.all().items():
            if key.startswith(prefix) and key.endswith("]"):
                field = key[len(prefix):-1]
                result[field] = value
        return result

    def input(self, key, default=None, cast: type = None) -> Any:
        value = None

        if "[]" in key:
            if key in self.request.form:
                value = self.request.form.getlist(key)
            elif key in self.request.args:
                value = self.request.args.getlist(key)

        elif key in self.request.view_args:
            value = self.request.view_args[key]

        elif key in self.request.args:
            value = self.request.args[key]

        elif self.request.method == "POST" and key in self.request.form:
            value = self.request.form[key]

        elif self.request.content_type == 'application/json' and key in self.request.json:
            value = self.request.json[key]

        # Nothing found
        if value is None:
            return default

        # Auto-cast if type is provided
        if cast:
            try:
                if cast is bool:
                    def to_bool(v):
                        return str(v).lower() in ["true", "1", "yes", "on"]

                    if isinstance(value, list):
                        return [to_bool(v) for v in value]
                    return to_bool(value)

                if cast == "date":
                    return self.date(key, default)
                elif cast == "datetime":
                    return self.datetime_(key, default)
                elif cast == "time":
                    return self.time(key, default)

                if isinstance(value, list):
                    return [cast(v) for v in value]
                return cast(value)

            except (ValueError, TypeError):
                return default

        return value

    def view_args(self, key, default=None) -> Any:
        return self.request.view_args.get(key, default)

    def query(self, key, default=None) -> Any:
        if "[]" in key:
            if key in self.request.args:
                return self.request.args.getlist(key)
        return self.request.args.get(key, default)

    def string(self, key, default=None) -> str:
        return str(self.input(key, default))

    def integer(self, key, default=None) -> int:
        return self.input(key, default, cast=int)

    def float(self, key, default=None) -> float:
        return self.input(key, default, cast=float)

    def to_list(self, key, default=None, cast: type = str) -> list:
        val = self.input(key, default)
        if isinstance(val, str):
            val = val.split(",")
        if isinstance(val, list) and cast:
            try:
                return [cast(v) for v in val]
            except Exception:
                return val
        return val

    def lists(self) -> dict:
        return {k.rstrip("[]"): v for k, v in self.all().items() if k.endswith("[]")}

    def checkbox(self, key, default=False):
        return key in self.all()

    def boolean(self, key, default=None) -> bool:
        return self.input(key, default, cast=bool)

    def date(self, key: str, default=None):
        val = self.input(key)
        if not val:
            return default

        for fmt in COMMON_DATE_FORMATS:
            try:
                return datetime.strptime(val, fmt).date()
            except (ValueError, TypeError):
                continue
        return default

    def datetime_(self, key: str, default=None, tz: str = "UTC", to_utc=True) -> datetime:
        val = self.input(key)
        if not val:
            return default

        for fmt in COMMON_DATETIME_FORMATS:
            try:
                dt = datetime.strptime(val, fmt).replace(tzinfo=ZoneInfo(tz))
                return dt.astimezone(timezone.utc) if to_utc else dt
            except (ValueError, TypeError):
                continue
        return default

    def now(self, tz: str = "UTC") -> datetime:
        return datetime.now(ZoneInfo(tz))

    def today(self, tz: str = "UTC") -> datetime.date:
        return self.now(tz).date()

    def tomorrow(self, tz: str = "UTC") -> datetime.date:
        return self.today(tz) + timedelta(days=1)

    def yesterday(self, tz: str = "UTC") -> datetime.date:
        return self.today(tz) - timedelta(days=1)

    def days_ago(self, days: int, tz: str = "UTC") -> datetime.date:
        return self.today(tz) - timedelta(days=days)

    def days_in_future(self, days: int, tz: str = "UTC") -> datetime.date:
        return self.today(tz) + timedelta(days=days)

    def start_of_week(self, tz: str = "UTC", week_start: int = 0) -> datetime.date:
        """
        Get the start of the current week.
        week_start: 0 = Monday, 6 = Sunday
        """
        today = self.today(tz)
        return today - timedelta(days=(today.weekday() - week_start) % 7)

    def weeks_ago(self, n: int, tz: str = "UTC") -> datetime.date:
        """
        Get the date n weeks ago from today.
        """
        return self.today(tz) - timedelta(weeks=n)

    def start_of_month(self, tz: str = "UTC") -> datetime.date:
        """
        Get the first day of the current month.
        """
        today = self.today(tz)
        return today.replace(day=1)

    def end_of_month(self, tz: str = "UTC") -> datetime.date:
        """
        Get the last day of the current month.
        """
        today = self.today(tz)
        last_day = monthrange(today.year, today.month)[1]
        return today.replace(day=last_day)

    def months_ago(self, n: int, tz: str = "UTC") -> datetime.date:
        """
        Get the first day of the month n months ago.
        """
        today = self.today(tz)
        year = today.year
        month = today.month - n

        while month <= 0:
            month += 12
            year -= 1

        return today.replace(year=year, month=month, day=1)

    def time(self, key: str, default=None) -> dtime:
        val = self.input(key)
        if not val:
            return default

        for fmt in COMMON_TIME_FORMATS:
            try:
                return datetime.strptime(val, fmt).time()
            except (ValueError, TypeError):
                continue
        return default

    def all(self) -> dict:
        data = {
            **self.request.view_args,
            **self.request.args,
            **self.request.form,
            **self.__get_json()
        }

        # Extract list-style keys from both args and form
        list_params = {}

        for key in set(list(self.request.args.keys()) + list(self.request.form.keys())):
            if key.endswith("[]"):
                if key in self.request.form:
                    list_params[key] = self.request.form.getlist(key)
                elif key in self.request.args:
                    list_params[key] = self.request.args.getlist(key)

        data.update(list_params)

        return {key: value for key, value in data.items() if value != ''}

    def grouped(self, prefix: str = None, sort: bool = True, as_list: bool = True):
        """
        Groups params with array-style or table-style nesting.

        Supports:
        - filters[0][field]=value  -> [{"field": "value"}]
        - PaymentTable[page]=2     -> {"PaymentTable": {"page": "2"}}
        - Prefix matching:
            • Exact: "PaymentTable"
            • Glob:  "*Table" or "Pay*"
            • Regex: r".*Table$"

        Args:
            prefix (str): Optional filter for main key (exact, glob, or regex).
            sort (bool): Sort grouped results by index (for array-style keys).
            as_list (bool): For array-style grouping, return list instead of dict.

        Returns:
            dict | list
        """
        groups = defaultdict(dict)

        # detect regex mode
        regex_mode = prefix and isinstance(prefix, str) and prefix.startswith("r")
        regex_pattern = None
        if regex_mode:
            try:
                regex_pattern = re.compile(prefix[1:])  # strip leading 'r'
            except re.error:
                regex_pattern = None

        for key, value in self.all().items():
            parts = key.split("[")
            if len(parts) < 2:
                continue

            main = parts[0]  # e.g. "PaymentTable" or "filters"

            # --- Apply filtering ---
            if prefix:
                if regex_pattern:
                    if not regex_pattern.match(main):
                        continue
                elif "*" in prefix or "?" in prefix:  # glob-style
                    if not fnmatch.fnmatch(main, prefix):
                        continue
                else:  # exact
                    if main != prefix:
                        continue

            inner = parts[1][:-1] if parts[1].endswith("]") else None
            if inner is None:
                continue

            # Array-style: filters[0][field]
            if inner.isdigit() and len(parts) >= 3:
                idx = int(inner)
                field = parts[2][:-1]
                groups[idx][field] = value

            # Table-style: PaymentTable[page]
            elif not inner.isdigit():
                groups[main][inner] = value

        # Format result
        if any(isinstance(k, int) for k in groups.keys()):
            return [groups[i] for i in sorted(groups)] if sort else dict(groups)
        return dict(groups)

    def only(self, keys: list | str) -> dict:
        if isinstance(keys, str):
            keys = [keys]
        return {key: value for key, value in self.all().items() if key in keys}

    def except_(self, keys: list | str) -> dict:
        if isinstance(keys, str):
            keys = [keys]
        return {key: value for key, value in self.all().items() if key not in keys}

    def is_image(self, key):
        file = self.file(key)
        return file and file.mimetype.startswith("image/")

    def get_locale(self):
        return self.headers("Accept-Language", "en").split(",")[0]

    def sanitize(self, key):
        raw = self.input(key, "")
        return re.sub(r"<.*?>", "", raw).strip()

    def has(self, key: str) -> bool:
        return key in self.all()

    def has_any(self, keys: list) -> bool:
        return any([key in self.all() for key in keys])

    def has_all(self, keys: list) -> bool:
        return all([key in self.all() for key in keys])

    def has_only(self, keys: list) -> bool:
        return self.has_all(keys) and len(self.all()) == len(keys)

    def when_has(self, key: str, callback, default=None):
        if self.has(key):
            return callback(self.input(key))
        return default

    def filled(self, key: str) -> bool:
        val = self.input(key)
        return val is not None and val != ''

    def is_not_filled(self, key: str | list) -> bool:
        if isinstance(key, str):
            return not self.filled(key)
        return all([not self.filled(k) for k in key])

    def any_filled(self, keys: list) -> bool:
        return any([self.filled(key) for key in keys])

    def when_filled(self, key: str, callback, default=None):
        if self.filled(key):
            return callback(self.input(key))
        return default

    def missing(self, key: str) -> bool:
        return not self.has(key)

    def when_missing(self, key: str, callback, default=None):
        if self.missing(key):
            return callback()
        return default

    def merge(self, data: dict) -> dict:
        return {**self.all(), **data}

    def merge_if_missing(self, data: dict) -> dict:
        return {**data, **self.all()}

    def path(self) -> str:
        return self.request.path

    def base_path(self) -> str:
        path = self.request.path.strip("/")
        parts = path.split("/", 1)
        return f"/{parts[0]}" if parts else "/"

    def url(self) -> str:
        return self.request.url

    @property
    def method(self) -> str:
        return self.request.method

    def headers(self, key: str = None, default=None) -> dict | str:
        if key:
            header = self.request.headers.get(key)
            return header if header else default
        return {key: value for key, value in self.request.headers}

    def host(self) -> str:
        return self.request.host

    def ip(self) -> str:
        return self.request.remote_addr

    def ips(self) -> list:
        return list(self.request.access_route)

    def get_acceptable_content_types(self) -> list:
        return self.headers('Accept').split(',')

    def accepts(self, content_type: str | list) -> bool:
        if isinstance(content_type, str):
            content_type = [content_type]
        return any([content in self.get_acceptable_content_types() for content in content_type])

    def expects_json(self) -> bool:
        return self.accepts('application/json')

    def is_method(self, method: str) -> bool:
        return self.request.method == method

    @property
    def request(self):
        return request

    def flash(self):
        self.request.flash(self.all(), "old")

    def flash_only(self, keys: list):
        self.request.flash(self.only(keys), "old")

    def flash_except(self, keys: list):
        self.request.flash(self.except_(keys), "old")

    def old(self, key: str, default=None) -> Any:
        val: list[tuple] = get_flashed_messages(True, "old")
        try:
            val: tuple = val[0]
            val: dict[str, Any] = val[1]
            return val.get(key, default)
        except IndexError:
            return default

    def session(self):
        return self.request.session

    def cookie(self, key: str, default=None) -> Any:
        return self.request.cookies.get(key, default)

    def has_cookie(self, key: str) -> bool:
        return key in self.request.cookies

    def file(self, key: str, default=None, multiple=False):
        if not multiple:
            val = self.request.files.get(key, default)
            if val:
                return UploadedFile(
                    stream=val.stream,
                    filename=val.filename,
                    name=val.name,
                    content_type=val.content_type
                )
            return val
        else:
            files = self.request.files.getlist(key)
            if files:
                return [UploadedFile(
                    stream=file.stream,
                    filename=file.filename,
                    name=file.name,
                    content_type=file.content_type
                ) for file in files]
            return files

    def has_file(self, key: str) -> bool:
        return key in self.request.files

    def csrf_token(self, key="csrf_token") -> str:
        token = secrets.token_urlsafe(32)
        session[key] = token
        return token

    def validate_csrf(self, token: str, key="csrf_token") -> bool:
        return token and compare_digest(session.get(key), token)

    from urllib.parse import urlencode

    def clean_url(request, updates):
        """
        Removes and/or updates query params in a URL, ensuring no duplicate keys.

        Args:
            request: The request object with .all() and .path() methods.
            updates: Can be
                     - a tuple (key, value)
                     - a list of dicts, e.g. [{"page": 2}, {"filter": "active"}]
                     - a dict, e.g. {"PaymentTable[page]": 2}

        Returns:
            str: Cleaned URL with updated query params (deduplicated).
        """
        query_args = request.all().copy()

        # Apply updates
        if isinstance(updates, tuple) and len(updates) == 2:
            key, value = updates
            if value is None:
                query_args.pop(key, None)
            else:
                query_args[key] = value

        elif isinstance(updates, list):
            for d in updates:
                for key, value in d.items():
                    if value is None:
                        query_args.pop(key, None)
                    else:
                        query_args[key] = value

        elif isinstance(updates, dict):
            for key, value in updates.items():
                if value is None:
                    query_args.pop(key, None)
                else:
                    query_args[key] = value

        # --- Deduplicate ---
        # Convert everything into a dict of key → single value
        # If value is a list, only keep unique values (first occurrence wins).
        deduped_args = {}
        for key, value in query_args.items():
            if isinstance(value, list):
                if value:
                    deduped_args[key] = value[0]
            else:
                deduped_args[key] = value

        return f"{request.path()}?{urlencode(deduped_args)}"

    def clean_table_url(request, table, updates):
        """
        Convenience wrapper for clean_url that automatically
        expands updates into table[field] keys.

        Example:
            clean_table_url("PaymentTable", {"page": 2})
            -> adds "PaymentTable[page]=2"
        """
        return request.clean_url({f"{table}[{k}]": v for k, v in updates.items()})

    def validate(self, schema: dict[str, list]) -> dict[str, list[str]]:
        errors = {}
        data = self.all()

        for field, rules in schema.items():
            value = self.input(field)

            for rule in rules:
                rule_fn = None
                message = None

                # Rule can be string, function, or (function, message)
                if isinstance(rule, str):
                    rule_fn = get_rule(rule)
                elif isinstance(rule, tuple) and callable(rule[0]):
                    rule_fn, message = rule
                elif callable(rule):
                    rule_fn = rule

                if not rule_fn:
                    continue

                try:
                    # Pass correct arg count
                    if rule_fn.__code__.co_argcount == 3:
                        valid = rule_fn(field, value, data)
                    elif rule_fn.__code__.co_argcount == 2:
                        valid = rule_fn(field, value)
                    else:
                        valid = rule_fn(value)

                    # If validation failed
                    if not valid:
                        errors.setdefault(field, []).append(
                            message or f"{field} is invalid"
                        )

                except Exception:
                    errors.setdefault(field, []).append(
                        message or f"{field}: validation error"
                    )

        return errors

    def bind_to(self, cls, defaults: dict = {}, cast: bool = True):
        if not is_dataclass(cls):
            raise ValueError("bind_to only supports dataclasses at this time.")

        data = self.all()
        # Normalize list-style keys like 'AccountsToLink[]'
        normalized_data = {
            (k.rstrip("[]") if k.endswith("[]") else k): v
            for k, v in data.items()
        }

        kwargs = {}

        for field in fields(cls):
            key = field.name
            val = normalized_data.get(key, defaults.get(key, field.default))

            if cast and field.type != Any and val is not None:
                try:
                    if hasattr(field.type, '__origin__') and field.type.__origin__ is list:
                        inner_type = field.type.__args__[0]
                        if isinstance(val, str):
                            val = val.split(",")
                        val = [inner_type(v) for v in val]
                    else:
                        val = field.type(val)
                except Exception:
                    pass

            kwargs[key] = val

        obj = cls(**kwargs)
        obj.as_dict = lambda: asdict(obj)
        return obj
