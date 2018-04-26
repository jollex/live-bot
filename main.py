import asyncio
import constants
import datetime
import discord
import logging
import pytz
import twitch

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

CHANNEL_ID = constants.TEST_CHANNEL_ID

discord_client = discord.Client()
twitch_client = twitch.TwitchClient(client_id=constants.TWITCH_ID)

@discord_client.event
async def on_ready():
    print('Logged in to servers:')
    for server in discord_client.servers:
        print('%s | %s' % (server, server.id))

@discord_client.event
async def on_member_update(before, after):
    if member_streaming(after) and not member_streaming(before):
        name = after.name if after.nick is None else after.nick
        url = after.game.url
        user = url.split('/')[-1]
        stream = get_stream(user)

        message = constants.MESSAGE_TEXT % (name, stream.game, url)
        embed = get_embed(url, user, stream)
        await discord_client.send_message(discord.Object(CHANNEL_ID), content=message, embed=embed)

def member_streaming(member):
    return member.game is not None and\
           member.game.type == 1

def get_embed(url, user, stream):
    embed = discord.Embed(title=url,
                          type=constants.EMBED_TYPE,
                          url=url,
                          timestamp=datetime.datetime.now(pytz.timezone('US/Pacific')),
                          color=constants.EMBED_COLOR)
    embed.set_footer(text=constants.FOOTER_TEXT)
    image_url = stream.channel.profile_banner if stream.preview is None else stream.preview['large']
    embed.set_image(url=image_url)
    embed.set_thumbnail(url=stream.channel.logo)
    embed.set_author(name=constants.AUTHOR_TEXT % user,
                     url=url,
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

def get_stream(user):
    user_id = twitch_client.users.translate_usernames_to_ids([user])[0].id
    stream = twitch_client.streams.get_stream_by_user(user_id)
    return stream

discord_client.run(constants.DISCORD_TOKEN)
