import pprint

from framework1.database.ActiveRecord import ActiveRecord
from framework1.database.fields.Fields import IntegerField, CharField, BooleanField, TextField



class InformationSchema(ActiveRecord):
    __table__ = "INFORMATION_SCHEMA.COLUMNS"
    __database__ = "PaymentsDatabase"
    __primary_key__ = "id"
    __driver__ = "mysql"

    COLUMN_NAME = CharField(max_length=255, nullable=True)


if __name__ == '__main__':
    payees = InformationSchema().all()
    pprint.pp(payees)