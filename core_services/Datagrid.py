from collections import defaultdict
from operator import itemgetter


class Datagrid:
    data = []

    def of(self, data):
        self.data = data
        return self

    def search(self, key, value):
        return [d for d in self.data if d[key] == value]

    def filter(self, key, value):
        return [d for d in self.data if d[key] != value]

    def paginate(self, page, page_size):
        # Calculate the start and end indices for the current page
        start = (page - 1) * page_size
        end = start + page_size

        # Return the slice of the data that corresponds to the page
        return self.data[start:end]

    def group(self, key):
        chunks = defaultdict(list)

        for item in self.data:
            # Use the value of the specified key to group the items
            chunks[item[key]].append(item)

        return dict(chunks)

    def sort(self, key, reverse=False):
        return sorted(self.data, key=itemgetter(key), reverse=reverse)
