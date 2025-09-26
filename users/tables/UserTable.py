from framework1.dsl.Table import Table, TextColumn
from lib.handlers.users.models.User import User

class UserTable(Table):
    model = User
    table_class = "table table-striped table-hover mt-3"

    def schema(self):
        return [
            TextColumn('id'),
            
        ]


        