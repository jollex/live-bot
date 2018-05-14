from secrets import *

DISCORD_STREAMING_TYPE = 1

MESSAGE_TEXT = '%s is live with %s, tune in now! %s'
OFFLINE_MESSAGE_TEXT = '**%s** is **offline**.'

EMBED_TYPE = 'rich'
EMBED_COLOR = 6570404

FOOTER_TEXT = 'Created by @jawlecks | Last updated'
FOOTER_ICON_URL = 'https://cdn.discordapp.com/emojis/328751425666547725.png'

AUTHOR_TEXT = '%s is now streaming!'
AUTHOR_OFFLINE_TEXT = '%s was streaming.'
AUTHOR_ICON_URL = 'https://cdn.discordapp.com/emojis/287637883022737418.png'

IMAGE_WIDTH = 400
IMAGE_HEIGHT = 225

DB_NAME = 'sqlite:///messages.db'
TABLE_NAME = 'message'

STREAM_IDS_FILE = 'stream_ids.txt'
ROLE_IDS_FILE = 'role_ids.txt'

POLL_INTERVAL = 900 # seconds

MAX_LOGS = 7
LOG_DIR = 'logs/'
LOG_FILE = LOG_DIR + 'live-bot.log'