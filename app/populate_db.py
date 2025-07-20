from . import db
from .models import User


def add_initial_data():
    try:
        if not User.query.get(1):
            user_id_1 = User(id=1, username='tester', email='tester@fake.com', password='tester')
            db.session.add(user_id_1)
            db.session.commit()
    except Exception as e:
        print("skipping initialization")