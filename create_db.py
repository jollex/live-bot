import constants
import dataset

def create_db(db_name):
    db = dataset.connect('sqlite:///%s' % db_name)
    table = db.create_table(constants.TABLE_NAME)
    table.create_column('message_id', db.types.integer)
    table.create_column('stream', db.types.text)
    table.create_column('live', db.types.boolean)
    return table

create_db(constants.DB_NAME)