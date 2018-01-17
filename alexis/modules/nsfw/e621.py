from urllib.parse import urlencode
from random import choice

from alexis import Command
from alexis.base.utils import img_embed


class E621(Command):
    def __init__(self, bot):
        super().__init__(bot)
        self.name = 'e621'
        self.nsfw_only = True

    async def handle(self, message, cmd):
        if cmd.argc < 1:
            await cmd.answer('formato: $PX$NM <texto de búsqueda>')
            return

        query = {
            'tags': cmd.text,
            'limit': 30
        }

        q_url = 'https://e621.net/post/index.json?' + urlencode(query)
        async with self.http.get(q_url) as r:
            posts = await r.json()
            if len(posts) == 0:
                await cmd.answer('sin resultados :c')
                return

            post = choice(posts)
            await cmd.answer(img_embed(post.get('file_url')))