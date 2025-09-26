import os

from framework1.database.ActiveRecord import ActiveRecord
from framework1.database.fields.Fields import IntegerField, CharField, DateTimeField
from framework1.database.active_record.utils.decorators import on
from lib.services.ClientDatabase import ClientDatabase

class User(ActiveRecord):
    __table__ = os.getenv("AUTH_DB_USER_REPO_TABLE", "users")
    __driver__ = "mssql"
    __database__ = ClientDatabase
    __primary_key__ = os.getenv("AUTH_DB_IDENTITY_COLUMN", "id")

    id = IntegerField(primary_key=True, auto_increment=True)
    Role = CharField(max_length=50, default="User")
    TenantId = CharField(max_length=50)
    Email = CharField(max_length=50)
    Username = CharField(max_length=50)
    BusinessPartyId = IntegerField()



if __name__ == "__main__":
    User.create_table()  # This will create the table directly
