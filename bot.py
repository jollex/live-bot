import constants

import asyncio
import dataset
import datetime
import discord
import logging
import pytz
import signal
import sys
import twitch

CHANNEL_ID = discord.Object(constants.TEST_CHANNEL_ID)

class LiveBot():
    def __init__(self):
        self.logger = self.init_logger()
        self.loop = asyncio.get_event_loop()

        self.discord = discord.Client()
        self.loop.run_until_complete(self.discord.login(constants.DISCORD_TOKEN))
        self.twitch = twitch.TwitchClient(client_id=constants.TWITCH_ID)
        self.db = dataset.connect(constants.DB_NAME)
        self.table = self.db[constants.TABLE_NAME]

        self.stream_ids = self.get_db_streams()
        with open(constants.STREAM_IDS_FILE, 'r') as f:
            self.stream_ids = set(self.stream_ids + f.read().split(','))

        self.role_ids = None
        with open(constants.ROLE_IDS_FILE, 'r') as f:
            self.role_ids = f.read().split(',')

        self.logger.debug('INITIALIZED')

    def run(self):
        try:
            tasks = [asyncio.ensure_future(self.listen()),
                     asyncio.ensure_future(self.poll())]
            self.loop.run_until_complete(asyncio.gather(*tasks))
        except KeyboardInterrupt:
            self.tear_down()
        finally:
            self.loop.close()

    async def listen(self):
        @self.discord.event
        async def on_member_update(before, after):
            if self.stream_change(before, after):
                user = after.game.url.split('/')[-1]
                stream_id = str(self.twitch.users.translate_usernames_to_ids([user])[0].id)
                self.stream_ids.append(stream_id)

        await self.discord.connect()

    def stream_change(self, before, after):
        return self.has_role(after)\
               and self.member_streaming(after)\
               and not self.member_streaming(before)

    def has_role(self, member):
        for role in member.roles:
            if role.id in self.role_ids:
                return True
        return False

    def member_streaming(self, member):
        return member.game is not None\
               and member.game.type == 1

    def get_db_streams(self):
        return [str(row['stream_id']) for row in self.table.find()]

    async def poll(self):
        while True:
            await self.poll_once()
            await asyncio.sleep(constants.POLL_INTERVAL)

    async def poll_once(self):
        self.logger.debug('POLLING')
        live_streams = self.twitch.streams.get_live_streams(','.join(self.stream_ids),
                                                            limit=100)
        live_stream_ids = [str(stream.channel.id) for stream in live_streams]
        db_streams = self.get_db_streams()

        self.logger.debug(live_stream_ids)
        self.logger.debug(db_streams)

        for stream in live_streams:
            stream_id = str(stream.channel.id)
            if stream_id in db_streams:
                message_id = self.table.find_one(stream_id=stream_id)['message_id']
                await self.update_stream(message_id, stream)
            else:
                await self.start_stream(stream)

        for stream_id in db_streams:
            if stream_id not in live_stream_ids:
                message_id = self.table.find_one(stream_id=stream_id)['message_id']
                await self.end_stream(message_id)            

    async def start_stream(self, stream):
        content = constants.MESSAGE_TEXT % (stream.channel.display_name,
                                            stream.channel.game,
                                            stream.channel.url)
        embed = self.get_embed(stream, False)
        message = await self.discord.send_message(CHANNEL_ID,
                                                  content=content,
                                                  embed=embed)

        row = dict(
            message_id=message.id,
            stream_id=stream.channel.id)
        self.table.insert(row)

    async def update_stream(self, message_id, stream):
        message = await self.get_message(message_id)
        embed = self.get_embed(stream, True)
        await self.discord.edit_message(message,
                                        embed=embed)

    async def end_stream(self, message_id):
        message = await self.get_message(message_id)
        stream_id = self.table.find_one(message_id=message_id)['stream_id']
        channel = self.twitch.channels.get_by_id(stream_id)

        content = constants.OFFLINE_MESSAGE_TEXT % channel.display_name
        embed = self.get_offline_embed(channel)
        await self.discord.edit_message(message,
                                        new_content=content,
                                        embed=embed)

        self.table.delete(message_id=message_id)

    async def get_message(self, message_id):
        return await self.discord.get_message(CHANNEL_ID, message_id)

    def get_embed(self, stream, update):
        embed = discord.Embed(title=stream.channel.url,
                              type=constants.EMBED_TYPE,
                              url=stream.channel.url,
                              timestamp=self.get_time(),
                              color=constants.EMBED_COLOR)
        footer = constants.FOOTER_UPDATED_TEXT if update else constants.FOOTER_STARTED_TEXT
        embed.set_footer(text=footer)
        image_url = stream.channel.profile_banner 
        if stream.preview is not None:
            image_url = stream.preview['template'].format(width=400, height=225)
        embed.set_image(url=image_url)
        embed.set_thumbnail(url=stream.channel.logo)
        embed.set_author(name=constants.AUTHOR_TEXT % stream.channel.display_name,
                         url=stream.channel.url,
                         icon_url=constants.AUTHOR_ICON_URL)
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
        embed = discord.Embed(title=channel.url,
                              type=constants.EMBED_TYPE,
                              url=channel.url,
                              timestamp=self.get_time(),
                              color=constants.EMBED_COLOR)
        embed.set_footer(text=constants.FOOTER_OFFLINE_TEXT)
        embed.clear_fields()
        embed.set_thumbnail(url=channel.logo)
        embed.set_author(name=constants.AUTHOR_OFFLINE_TEXT % channel.display_name,
                         url=channel.url,
                         icon_url=constants.AUTHOR_ICON_URL)
        return embed

    def get_time(self):
        return datetime.datetime.now(pytz.timezone('US/Pacific'))

    def init_logger(self):
        logger = logging.getLogger('discord')
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)
        return logger

    def tear_down(self):
        self.db.commit()
        self.loop.run_until_complete(self.discord.logout())

if __name__ == '__main__':
    lb = LiveBot()

    def sigterm_handler(signal, frame):
        lb.tear_down()
        sys.exit(0)

    lb.run()