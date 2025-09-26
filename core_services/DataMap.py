import pprint
from typing import Dict, Any, Literal

from framework1.core_services.Database import Database

DATAMAP_OPERATIONS: Literal['INSERT', 'UPDATE'] = "INSERT"

def UpdateOperation():
    return 'UPDATE'

def InsertOperation():
    return 'INSERT'

class DataMap:
    def __init__(self, table_name: str, database: Database):
        self.table_name = table_name
        self.data_dict = {}
        self.database = database

    def data(self, data: Dict[str, any]):
        """Specify the data to insert."""
        self.data_dict = data
        return self

    def table(self, table_name: str):
        self.table_name = table_name
        return self

    def database(self, database):
        self.database = database
        return self

    def only(self, *args):
        self.data_dict = {k: v for k, v in self.data_dict.items() if k in args}
        return self

    def except_(self, *args):
        self.data_dict = {k: v for k, v in self.data_dict.items() if k not in args}
        return self

    def criteria(self, *args):
        """Specify the criteria for the query."""
        self.criteria = args
        return self

    def build(self, parameter_markers="%s", operation: DATAMAP_OPERATIONS="INSERT") -> str:
        """Build and return the SQL insert query."""
        if not self.data_dict:
            raise ValueError("No data provided for insertion")

        # Build SQL query dynamically
        if operation == 'INSERT':
            columns = ", ".join(self.data_dict.keys())
            placeholders = ", ".join([f"{parameter_markers}" for key in self.data_dict.keys()])
            query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        elif operation == 'UPDATE':
            columns = ", ".join([f"{key} = {parameter_markers}" for key in self.data_dict.keys()])
            query = f"UPDATE {self.table_name} SET {columns}"

        values = tuple(list(self.data_dict.values()))
        if parameter_markers == "%s":
            return self.database.save(query, self.table_name, values)
        else:
            return self.database.save(query, *values)
