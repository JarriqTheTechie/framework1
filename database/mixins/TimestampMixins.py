from framework1.database.fields.Fields import DateTimeField

class TimestampMixin:
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)