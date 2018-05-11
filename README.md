# Live Bot
Live Bot is a discord bot that posts when users of a discord server go live. It was created to run in *The Collegiate Hub* discord server for collegiate Oveerwatch players.

The bot has multiple functionalities. First of all, it reads in a list of twitch stream IDs from `stream-ids.txt`. Using those IDs it polls twitch regularly and posts a message in a specified channel when any of the streams go online. In addition, when a member of the discord server starts streaming, their stream ID is added to the list of IDs that are polled. The bot uses a whitelist of discord role ids stored in `role-ids.txt` to determine which roles are tracked.

When polling, if a stream is still online, the message announcing that stream will be edited to display the current viewers, title, and preview image. When the stream goes offline the message is edited a final time.

## Requirements
* Python 3.5 or higher

## Installation
To deploy this bot follow these steps:
1. Clone this repo: `git clone git@github.com:jollex/live-bot.git`
2. Create a virtualenv with Python 3.5 or higher: `virtualenv env --python python3.5`
3. Activate the environment: `source env/bin/activate`
4. Install the required packages: `pip install -r requirements.txt`
5. Create the database: `python create_db.py`

## Configuration
#### Authentication Tokens and Channel ID
The first file you will need to create is `secrets.py`. This file needs the following values:
```python
DISCORD_TOKEN = 'your-token-here'
TWITCH_ID = 'your-twitch-id-here'
IMGUR_ID = 'your-imgur-id-here'
IMGUR_SECRET = 'your-imgur-secret-here'

CHANNEL_ID = 'your-channel-id-here'
```

To get a discord token, go to the [discord applications page](https://discordapp.com/developers/applications/me) and create a bot. Your discord token is the bot's 'Client Secret'.

To get a twitch ID, go to the [twitch applications page](https://dev.twitch.tv/dashboard/apps) and create an application. You can find your ID under 'Client ID'.

To get an imgur ID and secret, go to the [imgur applications page](https://api.imgur.com/oauth2/addclient) and create an application with 'OAuth 2 authorization without callback URL'. Copy the imgur client ID and secret.

The channel ID is simply the discord channel ID of the channel you want the stream announcements posted in. To get this, right click on the channel you want in discord and click 'Copy ID'.

#### Stream and Role IDs
If you wish to track a list of preset twitch streams, put all the stream IDs in `stream-ids.txt` on one line, separated by commas.

Similarly, to keep a whitelist of discord roles that are tracked in the discord server, put the role IDs in `role-ids.txt` on one line, separated by commas.
