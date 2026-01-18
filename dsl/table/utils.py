from framework1.database.ActiveRecord import ActiveRecord
from framework1.utilities.DataKlass import DataKlass


def record_to_dict(record) -> dict:
    if hasattr(record, "to_dict") and not isinstance(record, DataKlass):
        return record.to_dict()
    if hasattr(record, "to_dict") and isinstance(record, DataKlass):
        return record
    if isinstance(record, ActiveRecord):
        return record
    return record
