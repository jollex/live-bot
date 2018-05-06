from secrets import *

LOG_SEPARATOR = '---------------------------------'

MESSAGE_TEXT = '%s is live with %s, tune in now! %s'
OFFLINE_MESSAGE_TEXT = '**%s** is **offline**.'

EMBED_TYPE = 'rich'
EMBED_COLOR = 6570404

FOOTER_BASE_TEXT = 'Bot created by @jawlecks | %s'
FOOTER_STARTED_TEXT = FOOTER_BASE_TEXT % 'Stream started'
FOOTER_UPDATED_TEXT = FOOTER_BASE_TEXT % 'Last updated'
FOOTER_OFFLINE_TEXT = FOOTER_BASE_TEXT % 'Stream ended'

AUTHOR_TEXT = '%s is now streaming!'
AUTHOR_OFFLINE_TEXT = '%s was streaming.'
AUTHOR_ICON_URL = 'https://cdn.discordapp.com/emojis/287637883022737418.png'

IMAGE_WIDTH = 400
IMAGE_HEIGHT = 225

DB_NAME = 'sqlite:///messages.db'
TABLE_NAME = 'message'

STREAM_IDS_FILE = 'stream_ids.txt'
ROLE_IDS_FILE = 'role_ids.txt'

# seconds
POLL_INTERVAL = 300