from framework1.database.fields.Fields import DateTimeField

class SoftDeletesScope:
    deleted_at = DateTimeField(null=True)

    def apply(self):
        return self.builder.where_null("deleted_at")
