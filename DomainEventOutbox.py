from framework1.database.ActiveRecord import ActiveRecord
from framework1.database.fields.Fields import IntegerField, CharField, DateTimeField, TextField


class DomainEventOutbox(ActiveRecord):
    __table__ = "domain_event_outbox"
    __driver__ = "mysql"
    __database__ = "PaymentsDatabase"
    __primary_key__ = "id"

    id = IntegerField(primary_key=True, auto_increment=True)
    event_type = CharField(max_length=255)
    payload = TextField()
    published_at = DateTimeField(nullable=True)
    failed_at = DateTimeField(nullable=True)
    retry_count = IntegerField(default=0)
    created_at = DateTimeField(default="CURRENT_TIMESTAMP")

if __name__ == '__main__':
    DomainEventOutbox.create_table()