import constants

import aioimgur
import asyncio
import dataset
import datetime
import discord
import logging
import pytz
import twitch

CHANNEL_ID = discord.Object(constants.CHANNEL_ID)

class LiveBot():
    def __init__(self):
        self.logger = self.init_logger()
        self.loop = asyncio.get_event_loop()

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
        
        self.role_ids = self.load_file(constants.ROLE_IDS_FILE)

        self.update_preview = False

        self.logger.debug('INITIALIZED')

    def init_logger(self):
        handler = logging.FileHandler(filename='live-bot.log',
                                      encoding='utf-8',
                                      mode='a')
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
        try:
            with open(file, 'r') as f:
                self.logger.info('File %s loaded' % file)
                return f.read().split(',')
        except FileNotFoundError:
            self.logger.info('File %s not found' % file)
            return []

    def run(self):
        try:
            tasks = [asyncio.ensure_future(self.listen()),
                     asyncio.ensure_future(self.poll())]
            self.loop.run_until_complete(asyncio.gather(*tasks))
        except KeyboardInterrupt:
            self.loop.run_until_complete(self.tear_down())
        finally:
            self.loop.close()

    async def listen(self):
        @self.discord.event
        async def on_member_update(before, after):
            if self.stream_change(before, after):
                self.logger.info('Discord Member %s started streaming' % after)
                user = after.game.url.split('/')[-1]
                ids = self.twitch.users.translate_usernames_to_ids([user])
                stream_id = str(ids[0].id)
                name = after.nick or after.name
                self.stream_ids_map[stream_id] = name

        await self.discord.connect()

    def stream_change(self, before, after):
        return self.has_role(after)\
               and self.member_streaming(after)\
               and not self.member_streaming(before)

    def has_role(self, member):
        if len(self.role_ids) == 0:
            return True

        for role in member.roles:
            if role.id in self.role_ids:
                return True

        return False

    def member_streaming(self, member):
        return member.game is not None\
               and member.game.type == constants.DISCORD_STREAMING_TYPE

    async def poll(self):
        while True:
            start = self.loop.time()
            await self.poll_once()
            wait = constants.POLL_INTERVAL - (self.loop.time() - start)
            self.logger.info('WAITING for %s seconds' % wait)
            await asyncio.sleep(wait)

    async def poll_once(self):
        self.logger.info('POLLING')
        self.update_preview = not self.update_preview

        stream_ids = ','.join(self.stream_ids_map.keys())
        live_streams = self.twitch.streams.get_live_streams(stream_ids,
                                                            limit=100)
        live_stream_ids = [str(stream.channel.id) for stream in live_streams]
        db_streams = self.get_db_streams()

        self.logger.debug(live_stream_ids)
        self.logger.debug(db_streams)

        for stream in live_streams:
            stream_id = str(stream.channel.id)
            if stream_id in db_streams:
                message_id = self.get_message_id(stream_id)
                await self.update_stream(message_id, stream)
            else:
                await self.start_stream(stream, self.stream_ids_map[stream_id])

        for stream_id in db_streams:
            if stream_id not in live_stream_ids:
                message_id = self.get_message_id(stream_id)
                await self.end_stream(message_id,
                                      self.stream_ids_map[stream_id])

    def get_db_streams(self):
        return [str(row['stream_id']) for row in self.table.find()]

    def get_message_id(self, stream_id):
        return self.table.find_one(stream_id=stream_id)['message_id']

    async def start_stream(self, stream, name):
        name = name or stream.channel.display_name
        content = constants.MESSAGE_TEXT % (name,
                                            stream.channel.game,
                                            stream.channel.url)
        embed = await self.get_embed(stream, False)
        message = await self.discord.send_message(CHANNEL_ID,
                                                  content=content,
                                                  embed=embed)

        row = dict(
            message_id=message.id,
            stream_id=stream.channel.id)
        self.table.insert(row)

    async def update_stream(self, message_id, stream):
        message = await self.get_message(message_id)
        embed = await self.get_embed(stream, True, self.get_image_url(message))
        await self.discord.edit_message(message,
                                        embed=embed)

    def get_image_url(self, message):
        embed = message.embeds[0]
        return embed['image']['url']

    async def end_stream(self, message_id, name):
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
        return await self.discord.get_message(CHANNEL_ID, message_id)

    async def get_embed(self, stream, update, image_url=None):
        if update:
            footer = constants.FOOTER_UPDATED_TEXT
        else:
            footer = constants.FOOTER_STARTED_TEXT
        embed = self.get_base_embed(stream.channel,
                                    footer,
                                    constants.AUTHOR_TEXT)

        preview_url = stream.preview['template'].format(
            width=constants.IMAGE_WIDTH,
            height=constants.IMAGE_HEIGHT)
        image_url = image_url or preview_url
        if self.update_preview:
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
        embed = self.get_base_embed(channel,
                                    constants.FOOTER_OFFLINE_TEXT,
                                    constants.AUTHOR_OFFLINE_TEXT)
        return embed

    def get_base_embed(self, channel, footer, author_template):
        embed = discord.Embed(title=channel.url,
                              type=constants.EMBED_TYPE,
                              url=channel.url,
                              timestamp=self.get_time(),
                              color=constants.EMBED_COLOR)
        embed.set_thumbnail(url=channel.logo)
        embed.set_footer(text=footer,
                         icon_url=constants.FOOTER_ICON_URL)
        embed.set_author(name=author_template % channel.display_name,
                         url=channel.url,
                         icon_url=constants.AUTHOR_ICON_URL)
        return embed

    async def get_imgur_url(self, image_url):
        new_image = await self.imgur.upload_from_url(image_url)
        self.logger.debug('IMGUR RATE LIMITS:')
        for (k, v) in self.imgur.credits.items():
            self.logger.debug('  %s: %s' % (k, v)) 
        return new_image['link']

    def get_time(self):
        return datetime.datetime.now(pytz.timezone('US/Pacific'))

    async def tear_down(self):
        self.db.commit()
        await self.discord.logout()

if __name__ == '__main__':
    lb = LiveBot()
    lb.run()