"""The discord.py client: turns Gateway messages into Incoming and hands them on.

Features:
    US-WTY-06, F-03
"""

import discord
from meritum_backend.discord.constants import GATEWAY_INTENTS
from meritum_backend.discord.gateway._handler import (
    GatewayHandler,
    Incoming,
    strip_mention,
)


def incoming_from(
    message: discord.Message, bot: discord.abc.Snowflake
) -> Incoming | None:
    """The message to answer: a DM, or a server message that mentions the bot.

    Args:
        message: the Gateway's message.
        bot: the bot's own user.

    Returns:
        The message, or None for bots' messages and server chatter without a mention.

    Features:
        US-WTY-06, F-03
    """
    if message.author.bot:
        return None
    in_server = message.guild is not None
    if in_server and not any(user.id == bot.id for user in message.mentions):
        return None
    # no MESSAGE_CONTENT intent: Discord still sends the content of DMs and mentions
    text = strip_mention(message.content, bot.id)
    # a voice message's attachment URL expires: the handler fetches it at once

    async def reply(content: str) -> None:
        if in_server:
            await message.reply(content, mention_author=False)
        else:
            await message.channel.send(content)

    voice = next((a.url for a in message.attachments if a.is_voice_message()), None)
    return Incoming(str(message.id), str(message.author.id), text, reply, voice)


class MeritumClient(discord.Client):
    """Gateway client with the intents mentions and DMs need, and nothing more.

    Args:
        handler: answers each message.

    Features:
        US-WTY-06, F-03
    """

    def __init__(self, handler: GatewayHandler) -> None:
        intents = discord.Intents.none()
        for name in GATEWAY_INTENTS:
            setattr(intents, name, True)
        # claim text comes from users: never let a reply ping @everyone or roles
        super().__init__(
            intents=intents, allowed_mentions=discord.AllowedMentions.none()
        )
        self._handler = handler

    async def on_message(self, message: discord.Message) -> None:
        """Answer the message when it is for the bot.

        Args:
            message: the Gateway's message.

        Features:
            US-WTY-06, F-03
        """
        if self.user is None:
            return
        incoming = incoming_from(message, self.user)
        if incoming is not None:
            await self._handler.handle(incoming)
