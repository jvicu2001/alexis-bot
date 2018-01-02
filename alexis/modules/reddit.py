import asyncio
import html
import re

import discord
import peewee
from discord import Embed

from alexis import Command
from alexis.base.database import BaseModel
from alexis.base.utils import pat_channel, pat_subreddit


class RedditFollow(Command):
    def __init__(self, bot):
        super().__init__(bot)
        self.name = 'reddit'
        self.help = 'Muestra la cantidad de posts (registrados por el bot) hechos por un redditor'
        self.db_models = [Redditor, Post, ChannelFollow]
        self.chans = {}
        self.allow_pm = False
        self.owner_only = True

    def on_loaded(self):
        self.load_channels()

    async def handle(self, message, cmd):
        if cmd.argc < 1:
            await cmd.answer('formato: $PX$NM (set|remove|list|posts)')
            return

        if cmd.args[0] == 'set' or cmd.args[0] == 'remove':
            if cmd.argc < 2:
                await cmd.answer('formato: $PX$NM {} <subreddit> [channel=actual]'.format(cmd.args[0]))
                return
            else:
                if not pat_subreddit.match(cmd.args[1]):
                    await cmd.answer('nombre de subreddit incorrecto')
                    return

                if cmd.argc > 2:
                    if not pat_channel.match(cmd.args[2]):
                        await cmd.answer('formato: $PX$NM add <subreddit> [channel=actual]')
                        return

                    channel = message.server.get_channel(cmd.args[2][2:-1])
                    if channel is None:
                        await cmd.answer('canal no encontrado aquí')
                        return
                else:
                    channel = message.channel

            if cmd.args[0] == 'set':
                chan, created = ChannelFollow.get_or_create(
                    subreddit=cmd.args[1], serverid=message.server.id, channelid=channel.id)

                if created:
                    await cmd.answer('subreddit agregado')
                    if chan.subreddit not in self.chans:
                        self.chans[chan.subreddit] = []

                    self.chans[chan.subreddit].append((chan.serverid, chan.channelid))
                    return
                else:
                    await cmd.answer('ese subreddit ya estaba configurado para ese canal xd')
                    return
            else:
                try:
                    asd = ChannelFollow.get(ChannelFollow.subreddit == cmd.args[1],
                                            ChannelFollow.serverid == message.server.id,
                                            ChannelFollow.channelid == channel.id)
                    asd.delete_instance()

                    if cmd.args[1] in self.chans:
                        self.chans[cmd.args[1]].remove((message.server.id, channel.id))
                        if len(self.chans[cmd.args[1]]) == 0:
                            del self.chans[cmd.args[1]]

                    await cmd.answer('subreddit desactivado del canal seleccionado')
                    return
                except ChannelFollow.DoesNotExist:
                    await cmd.answer('el subreddit no está configurado en el canal seleccionado')
                    return
        elif cmd.args[0] == 'list':
            res = ChannelFollow.select().where(ChannelFollow.serverid == message.server.id)
            resp = []
            for chan in res:
                resp.append('- **{}** \➡ <#{}>'.format(chan.subreddit, chan.channelid))

            if len(res) == 0:
                await cmd.answer('no hay subs por seguir')
            else:
                await cmd.answer('subreddits a seguir:\n{}'.format('\n'.join(resp)))
        elif cmd.args[0] == 'posts':
            if cmd.argc < 2:
                await cmd.answer('formato: $PX$NM posts <redditor>')
                return

            user = cmd.args[1]
            if user.startswith('/u/'):
                user = user[3:]

            num_posts = get_user_posts(user)

            if num_posts > 0:
                text = '**/u/{name}** ha creado **{num}** post{s}.'
                await cmd.answer(text.format(name=user, num=num_posts, s=['s', ''][bool(num_posts == 1)]))
            else:
                text = '**/u/{name}** no ha creado ningún post.'.format(name=user)
                await cmd.answer(text)
        else:
            await cmd.answer('formato: $PX$NM (set|remove|posts)')

    async def task(self):
        post_id = ''
        await self.bot.wait_until_ready()
        try:
            for (subname, chans) in self.chans.items():
                subchannels = [chanid for svid, chanid in chans]
                posts = await get_posts(self.bot, subname)

                if len(posts) == 0:
                    continue

                data = posts[0]

                try:
                    exists = Post.get(Post.id == data['id'])
                except Post.DoesNotExist:
                    exists = False

                redditor, _ = Redditor.get_or_create(name=data['author'].lower())

                while data['id'] != post_id and not exists:
                    message = 'Nuevo post en **/r/{}**'.format(data['subreddit'])
                    embed = post_to_embed(data)

                    for channel in subchannels:
                        await self.bot.send_message(discord.Object(id=channel), content=message, embed=embed)

                    post_id = data['id']
                    if not exists:
                        Post.create(id=post_id, permalink=data['permalink'], over_18=data['over_18'])
                        self.bot.log.info('Nuevo post en /r/{subreddit}: {permalink}'.format(
                            subreddit=data['subreddit'], permalink=data['permalink']))

                        Redditor.update(posts=Redditor.posts + 1).where(
                            Redditor.name == data['author'].lower()).execute()

        except Exception as e:
            if isinstance(e, RuntimeError):
                pass
            self.bot.log.exception(e)
        finally:
            await asyncio.sleep(15)

        if not self.bot.is_closed:
            self.bot.loop.create_task(self.task())

    def load_channels(self):
        for chan in ChannelFollow.select():
            if chan.subreddit not in self.chans:
                self.chans[chan.subreddit] = []

            self.chans[chan.subreddit].append((chan.serverid, chan.channelid))


def get_user_posts(user):
    if not re.match('^[a-zA-Z0-9_-]*$', user):
        return None

    redditor, _ = Redditor.get_or_create(name=user.lower())
    return redditor.suffix


async def get_posts(bot, sub, since=0):
    url = 'https://www.reddit.com/r/{}/new/.json'.format(sub)
    req = bot.http_session.get(url)
    async with req as r:
        if not r.status == 200:
            return []

        posts = []
        data = await r.json()
        for post in data['data']['children']:
            if since < post['data']['created']:
                posts.append(post['data'])

        return posts


def post_to_embed(post):
    embed = Embed()
    embed.title = post['title']
    embed.set_author(name='/u/' + post['author'], url='https://www.reddit.com/user/' + post['author'])
    embed.url = 'https://www.reddit.com' + post['permalink']

    if post['is_self']:
        if len(post['selftext']) > 2048:
            embed.description = post['selftext'][:2044] + '...'
        else:
            embed.description = post['selftext']
    elif post['media']:
        if 'preview' in post:
            embed.set_image(url=html.unescape(post['preview']['images'][0]['source']['url']))
        else:
            embed.set_thumbnail(url=html.unescape(post['thumbnail']))
        embed.description = "Link del multimedia: " + post['url']
    elif 'preview' in post:
        embed.set_image(url=html.unescape(post['preview']['images'][0]['source']['url']))
    elif post['thumbnail'] != '':
        embed.set_thumbnail(url=html.unescape(post['thumbnail']))

    return embed


class Post(BaseModel):
    id = peewee.CharField()
    permalink = peewee.CharField(null=True)
    over_18 = peewee.BooleanField(default=False)


class Redditor(BaseModel):
    name = peewee.TextField()
    posts = peewee.IntegerField(default=0)


class ChannelFollow(BaseModel):
    subreddit = peewee.TextField()
    serverid = peewee.TextField()
    channelid = peewee.TextField()
