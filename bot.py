import constants

import aioimgur
import asyncio
import dataset
import datetime
import discord
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import pytz
import twitch

CHANNEL_ID = discord.Object(constants.CHANNEL_ID)

class LiveBot():
    """Discord bot that posts when streams go live and updates with metadata."""

    def __init__(self):
        """Initialize the bot.
        
        Initialize logging and all clients. Get reference to event loop. Load
        stream and role id files.
        """
        self.logger = self.init_logger()

        self.loop = asyncio.get_event_loop()

        # initialize clients for discord, twitch, database, and imgur
        self.discord = discord.Client()
        self.loop.run_until_complete(
            self.discord.login(constants.DISCORD_TOKEN))
        self.twitch = twitch.TwitchClient(client_id=constants.TWITCH_ID)
        self.db = dataset.connect(constants.DB_NAME)
        self.table = self.db[constants.TABLE_NAME]
        self.imgur = aioimgur.ImgurClient(constants.IMGUR_ID,
                                          constants.IMGUR_SECRET)

        stream_ids = self.get_db_streams() +\
                     self.load_file(constants.STREAM_IDS_FILE)
        self.stream_ids_map = {stream_id: None for stream_id in stream_ids}
        """dict of str to str or None: map of stream ids to discord display
        names or None if no discord account is linked to that stream.
        """
        
        #: list of str: list of role ids that members must have one or more of
        self.role_ids = self.load_file(constants.ROLE_IDS_FILE)

        self.logger.debug('INITIALIZED')

    def init_logger(self):
        """Initialize log handler for discord, asyncio, and this class.

        Returns:
            logging.Logger: Logger for this class.
        """
        if not os.path.isdir(constants.LOG_DIR):
            os.makedirs(constants.LOG_DIR)

        handler = TimedRotatingFileHandler(
            constants.LOG_FILE,
            when='midnight',
            backupCount=constants.MAX_LOGS,
            encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))

        discord_logger = logging.getLogger('discord')
        discord_logger.setLevel(logging.DEBUG)
        discord_logger.addHandler(handler)

        async_logger = logging.getLogger('asyncio')
        async_logger.setLevel(logging.DEBUG)
        async_logger.addHandler(handler)

        logger = logging.getLogger('live-bot')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        return logger

    def load_file(self, file):
        """Load contents of the given file.

        The file must contain comma-separated values.

        Args:
            file (str): The path to the file

        Returns:
            list: The values in the file or the empty list if the file was not
            found.
        """
        try:
            with open(file, 'r') as f:
                self.logger.info('File %s loaded' % file)
                return f.read().split(',')
        except FileNotFoundError:
            self.logger.info('File %s not found' % file)
            return []

    def run(self):
        """Run the bot.

        Create two tasks, one that listens to discord events and watches for
        users to start streaming, and one that polls twitch with all current
        stream ids at a set interval and sends/edits messages in discord. This
        function runs until it receives a KeyboardInterrupt.
        """
        try:
            tasks = [asyncio.ensure_future(self.listen()),
                     asyncio.ensure_future(self.poll())]
            self.loop.run_until_complete(asyncio.gather(*tasks))
        except KeyboardInterrupt:
            self.loop.run_until_complete(self.tear_down())
        finally:
            self.loop.close()

    async def listen(self):
        """Start listening to member update events from discord."""
        @self.discord.event
        async def on_member_update(before, after):
            """Callback for when a discord member update event is received.

            On member update, if the member was not streaming before and is now
            streaming their stream id is found and added to the stream id map
            with the value being their discord nickname or username.

            Args:
                before (discord.Member): The member before the update.
                after  (discord.Member): The member after the update.
            """
            if self.stream_change(before, after):
                self.logger.info('Discord Member %s started streaming' % after)
                user = after.game.url.split('/')[-1]
                ids = self.twitch.users.translate_usernames_to_ids([user])
                stream_id = str(ids[0].id)
                name = after.nick or after.name
                self.stream_ids_map[stream_id] = name

        # Start listening.
        self.logger.debug('CONNECTING to discord')
        await self.discord.connect()

    def stream_change(self, before, after):
        """Return whether or not a member has started streaming.

        Args:
            before (discord.Member): The member before the update.
            after  (discord.Member): The member after the update.

        Retuns:
            True if the member started streaming, False otherwise.
        """
        return self.has_role(after)\
               and self.member_streaming(after)\
               and not self.member_streaming(before)

    def has_role(self, member):
        """Return whether or not the given member has any of the needed roles.

        Args:
            member (discord.Member): The member to check for roles.

        Returns:
            True if the member has any of the roles or if there are no roles,
            False otherwise.
        """
        if len(self.role_ids) == 0:
            return True

        for role in member.roles:
            if role.id in self.role_ids:
                return True

        return False

    def member_streaming(self, member):
        """Return whether or not the given member is currently streaming.

        Args:
            member (discord.Member): The member to check.

        Returns:
            True if the member is streaming, False otherwise.
        """
        return member.game is not None\
               and member.game.type == constants.DISCORD_STREAMING_TYPE

    async def poll(self):
        """Poll twitch for live streams and update messages indefinitely.

        This function will run forever. Twitch is polled with all current stream
        ids and live streams are updated. Then the function sleeps for according
        to the poll interval and repeats.
        """
        while True:
            start = self.loop.time()
            await self.poll_once()
            sleep = constants.POLL_INTERVAL - (self.loop.time() - start)
            self.logger.info('SLEEPING for %s seconds' % sleep)
            await asyncio.sleep(sleep)

    async def poll_once(self):
        """Polls twitch and updates discord messages for live/ended streams."""
        self.logger.info('POLLING')

        stream_ids = ','.join(self.stream_ids_map.keys())
        live_streams = self.twitch.streams.get_live_streams(stream_ids,
                                                            limit=100)
        live_stream_ids = [str(stream.channel.id) for stream in live_streams]
        db_streams = self.get_db_streams()

        self.logger.debug(live_stream_ids)
        self.logger.debug(db_streams)

        await self.update_live_streams(db_streams, live_streams)
        await self.update_ended_streams(db_streams, live_stream_ids)

    async def update_live_streams(self, db_streams, live_streams):
        """Start any streams that went live and update already live streams.

        If a stream id is in live_streams and db_streams it means we already
        posted a message to discord about it so we update that message with the
        current stream stats.

        If a stream id is in live_streams and not in db_streams that means it
        went live during the last sleep period so we post the first message for
        that stream.

        Args:
            db_streams (list of str): List of live streams we have already
                posted messages for.
            live_streams (list of twitch.Stream): List of streams currently live
                from twitch.
        """
        for stream in live_streams:
            stream_id = str(stream.channel.id)
            if stream_id in db_streams:
                self.logger.debug('UPDATING %s' % stream_id)
                message_id = self.get_message_id(stream_id)
                await self.update_stream(message_id, stream)
            else:
                self.logger.debug('STARTING %s' % stream_id)
                await self.start_stream(stream, self.stream_ids_map[stream_id])

    async def update_ended_streams(self, db_streams, live_stream_ids):
        """Update messages for streams that ended.

        If a stream id is in db_streams and not live_streams that means it went
        offline during the last sleep period so we update the message to say the
        stream went offline and remove the stream from the database.

        Args:
            db_streams (list of str): List of live streams we have already
                posted messages for.
            live_stream_ids (list of str): List of stream ids currently live.
        """
        for stream_id in db_streams:
            if stream_id not in live_stream_ids:
                self.logger.debug('ENDING %s' % stream_id)
                message_id = self.get_message_id(stream_id)
                await self.end_stream(message_id,
                                      self.stream_ids_map[stream_id])

    def get_db_streams(self):
        """list of str: All stream ids in the database."""
        return [str(row['stream_id']) for row in self.table.find()]

    def get_message_id(self, stream_id):
        """Get message id for the given stream id.

        Args:
            stream_id (str): The stream id.

        Returns:
            str: The message id associated with that stream id.
        """
        return self.table.find_one(stream_id=stream_id)['message_id']

    async def start_stream(self, stream, name):
        """Performs all actions associated with a stream going live.

        A message is sent to discord with the current stream metadata. A row is
        added to the database with the stream's id and the id of the message
        that was sent.

        Args:
            stream (twitch.Stream): The metadata for the stream.
            name (str): The user's discord name or None.
        """
        name = name or stream.channel.display_name
        content = constants.MESSAGE_TEXT % (name,
                                            stream.channel.game,
                                            stream.channel.url)
        embed = await self.get_live_embed(stream)
        message = await self.discord.send_message(CHANNEL_ID,
                                                  content=content,
                                                  embed=embed)

        row = dict(
            message_id=message.id,
            stream_id=stream.channel.id)
        self.table.insert(row)

    async def update_stream(self, message_id, stream):
        """Updates the discord message with new stream metadata.

        Args:
            message_id (str): The message id of the message to edit.
            stream (twitch.Stream): The twitch stream metadata for the stream.
        """
        message = await self.get_message(message_id)
        embed = await self.get_live_embed(stream)
        await self.discord.edit_message(message,
                                        embed=embed)

    async def end_stream(self, message_id, name):
        """Performs all actions associated with a stream going offline.

        The discord message is edited one final time with an offline message.
        The message and associated stream id are removed from the database.

        Args:
            message_id (str): The message id of the message to edit.
            name (str): The username of the user who went offline or None.
        """
        message = await self.get_message(message_id)
        stream_id = self.table.find_one(message_id=message_id)['stream_id']
        channel = self.twitch.channels.get_by_id(stream_id)

        name = name or channel.display_name
        content = constants.OFFLINE_MESSAGE_TEXT % name
        embed = self.get_offline_embed(channel)
        await self.discord.edit_message(message,
                                        new_content=content,
                                        embed=embed)

        self.table.delete(message_id=message_id)

    async def get_message(self, message_id):
        """discord.Message: Return the message for the given message id."""
        return await self.discord.get_message(CHANNEL_ID, message_id)

    async def get_live_embed(self, stream):
        """Create the embed for the live stream message.

        Args:
            stream (twitch.Stream): The metadata for the stream.

        Returns:
            discord.Embed: The embed.
        """
        embed = self.get_base_embed(stream.channel,
                                    constants.AUTHOR_TEXT)

        preview_url = stream.preview['template'].format(
            width=constants.IMAGE_WIDTH,
            height=constants.IMAGE_HEIGHT)
        image_url = await self.get_imgur_url(preview_url)
        embed.set_image(url=image_url)
        
        embed.add_field(name='Now Playing',
                        value=stream.game,
                        inline=False)
        embed.add_field(name='Stream Title',
                        value=stream.channel.status,
                        inline=False)
        embed.add_field(name='Current Viewers',
                        value=stream.viewers,
                        inline=True)
        embed.add_field(name='Followers',
                        value=stream.channel.followers,
                        inline=True)

        return embed

    def get_offline_embed(self, channel):
        """Create the embed for the offline stream message.

        Args:
            channel (twitch.Channel): The metadata for the channel.

        Returns:
            discord.Embed: The embed.
        """
        embed = self.get_base_embed(channel,
                                    constants.AUTHOR_OFFLINE_TEXT)
        return embed

    def get_base_embed(self, channel, author_template):
        """Create the base embed for any message.

        Args:
            channel (twitch.Channel): The metadata for the channel.
            author_template (str): The string template to add the channel's
                name to.

        Returns:
            discord.Embed: The embed.
        """
        embed = discord.Embed(title=channel.url,
                              type=constants.EMBED_TYPE,
                              url=channel.url,
                              timestamp=self.get_time(),
                              color=constants.EMBED_COLOR)
        embed.set_thumbnail(url=channel.logo)
        embed.set_footer(text=constants.FOOTER_TEXT,
                         icon_url=constants.FOOTER_ICON_URL)
        embed.set_author(name=author_template % channel.display_name,
                         url=channel.url,
                         icon_url=constants.AUTHOR_ICON_URL)
        return embed

    async def get_imgur_url(self, image_url):
        """Upload the given image url to imgur and return the new url.

        Args:
            image_url (str): The url to the image to upload.

        Returns:
            str: The url to the uploaded image.
        """
        new_image = await self.imgur.upload_from_url(image_url)
        self.logger.debug('IMGUR RATE LIMITS:')
        for (k, v) in self.imgur.credits.items():
            self.logger.debug('  %s: %s' % (k, v)) 
        return new_image['link']

    def get_time(self):
        """datetime.datetime: Return the time right now."""
        return datetime.datetime.now(pytz.timezone('US/Pacific'))

    async def tear_down(self):
        """Commit all changes to the database and disconnect from discord."""
        self.db.commit()
        await self.discord.logout()

if __name__ == '__main__':
    lb = LiveBot()
    lb.run()