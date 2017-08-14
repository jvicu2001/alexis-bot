class Command:
    def __init__(self, bot):
        self.bot = bot
        self.name = ''
        self.swhandler = None
        self.mention_handler = False
        self.help = ''
        self.allow_pm = True
        self.pm_error = 'Este comando no se puede usar via PM'
        self.owner_only = False
        self.owner_error = 'No puedes usar este comando'

    def parse(self, message):
        return Message(message, self.bot)

    def is_owner(self, member, server):
        if server is None:
            return False

        if member.id in self.bot.config['owners']:
            return True

        for role in member.roles:
            owner_role = server.id + "@" + role.id
            if owner_role in self.bot.config['owners']:
                return True

        return False


class Message:
    def __init__(self, message, bot):
        self.bot = bot
        self.message = message
        self.author_name = Message.final_name(message.author)
        self.is_pm = message.server is None
        self.own = message.author.id == bot.user.id

        allargs = message.content.replace('  ', '').split(' ')
        self.args = [] if len(allargs) == 1 else allargs[1:]
        self.cmdname = allargs[0][1:]
        self.text = ' '.join(self.args)

    async def answer(self, content):
        self.bot.log.debug('Sending message "%s" to %s', content, self.message.channel)
        await self.bot.send_message(self.message.channel, content)

    @staticmethod
    def final_name(user):
        return user.nick if hasattr(user, 'nick') and user.nick else user.name
