import constants
import dataset
import os

def create_db(db_name):
    if not os.path.isfile(db_name.split('///')[1]):
        db = dataset.connect(db_name)
        table = db.create_table(constants.TABLE_NAME,
    	    					primary_id='message_id',
    		    				primary_type=db.types.bigint)
        table.create_column('stream_id', db.types.text)

if __name__ == '__main__':
    create_db(constants.DB_NAME)