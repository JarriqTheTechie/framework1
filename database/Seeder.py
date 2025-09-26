from datetime import datetime


class Seeder:
    model = None
    data = []

    @classmethod
    def run(cls):
        if not cls.model or not cls.data:
            raise ValueError("Seeder must define 'model' and 'data'")

        for row in cls.data:
            # existing = cls.model().where(**row).first()
            # if existing:
            #     continue  # Avoid duplicate inserts
            instance = cls.model(**row)
            instance.save()
