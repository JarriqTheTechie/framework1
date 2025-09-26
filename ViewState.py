import pprint

from framework1.database.ActiveRecord import ActiveRecord
from framework1.database.fields.Fields import IntegerField, CharField, BooleanField, TextField, DateTimeField

from lib.services.PaymentsDatabase import PaymentsDatabase


class ViewState(ActiveRecord):
    __table__ = "viewstate"
    __database__ = PaymentsDatabase
    __primary_key__ = "id"
    __driver__ = "mysql"

    id = IntegerField(primary_key=True, auto_increment=True)
    name = CharField()
    url = TextField()
    is_global = BooleanField(default=False)
    belongs_to = CharField(nullable=True)
    created_at = DateTimeField(default="CURRENT_TIMESTAMP")
    updated_at = DateTimeField(default="CURRENT_TIMESTAMP")


if __name__ == '__main__':
    ViewState().create_table()
    #pprint.pp(payees)