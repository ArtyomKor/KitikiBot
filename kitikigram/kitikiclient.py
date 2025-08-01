import asyncio
import importlib
import inspect
import typing
from os import listdir

from telethon import TelegramClient, events, errors
from telethon.client.updates import Callback, EventBuilderDict
from telethon.events.common import EventBuilder
from telethon.tl import types, functions
from telethon.tl.types import *
from telethon.tl.types.messages import MessageReactionsList


class KitikiClient(TelegramClient):
    handlers = []

    def __init__(self, session: str, api_id: int, api_hash: str, *, plugins=None, before_start=None, **kwargs):
        self.me: User = None
        if plugins is None:
            plugins = []

        for plugin_dir in plugins:
            plugin_dir = plugin_dir.replace('\\', '.').replace("/", ".")
            for plugin in listdir(plugin_dir):
                if plugin.endswith('.py'):
                    plugin_name = plugin[:-3]
                    importlib.import_module(f"{plugin_dir}.{plugin_name}")
        super().__init__(session, api_id, api_hash, **kwargs)

        if before_start is not None:
            self.loop.run_until_complete(before_start(self))

        for handler in KitikiClient.handlers:
            self.add_plugin_event_handler(handler[0], handler[1])
        KitikiClient.handlers.clear()

    async def set_me(self):
        self.me = await self.get_me()

    def add_plugin_event_handler(self, callback: Callback, event: EventBuilder = None):
        self.add_event_handler(callback, event, True)

    def add_event_handler(
            self: 'KitikiClient',
            callback: Callback,
            event: EventBuilder = None,
            plugin: bool = False):
        """
        Registers a new event handler callback.

        The callback will be called when the specified event occurs.

        Arguments
            callback (`callable`):
                The callable function accepting one parameter to be used.

                Note that if you have used `telethon.events.register` in
                the callback, ``event`` will be ignored, and instead the
                events you previously registered will be used.

            event (`_EventBuilder` | `type`, optional):
                The event builder class or instance to be used,
                for instance ``events.NewMessage``.

                If left unspecified, `telethon.events.raw.Raw` (the
                :tl:`Update` objects with no further processing) will
                be passed instead.

            plugin (`bool`, optional):
                Special flag for handler in plugin

        Example
            .. code-block:: python

                from telethon import TelegramClient, events
                client = TelegramClient(...)

                async def handler(event):
                    ...

                client.add_event_handler(handler, events.NewMessage)
        """
        builders = events._get_handlers(callback)
        if builders is not None:
            for event in builders:
                self._event_builders.append((event, callback, plugin))
            return

        if isinstance(event, type):
            event = event()
        elif not event:
            event = events.Raw()

        self._event_builders.append((event, callback, plugin))

    def list_event_handlers(self: 'KitikiClient') \
            -> 'typing.Sequence[typing.Tuple[Callback, EventBuilder]]':
        """
        Lists all registered event handlers.

        Returns
            A list of pairs consisting of ``(callback, event)``.

        Example
            .. code-block:: python

                @client.on(events.NewMessage(pattern='hello'))
                async def on_greeting(event):
                    '''Greets someone'''
                    await event.reply('Hi')

                for callback, event in client.list_event_handlers():
                    print(id(callback), type(event))
        """
        return [(callback, event, plugin) for event, callback, plugin in self._event_builders]

    @classmethod
    def on(cls, event: EventBuilder):
        def decorator(f):
            KitikiClient.handlers.append([f, event])
            return f

        return decorator

    def start(self, *args, **kwargs):
        for handler in KitikiClient.handlers:
            self.add_event_handler(handler[0], handler[1])
        super().start(*args, **kwargs)
        self.loop.run_until_complete(self.set_me())

    async def send_react(self,
                         chat: InputPeerEmpty | InputPeerSelf | InputPeerChat | InputPeerUser | InputPeerChannel | InputPeerUserFromMessage | InputPeerChannelFromMessage,
                         message_id: int, reaction: ReactionEmpty | ReactionEmoji | ReactionCustomEmoji | ReactionPaid):
        await self(functions.messages.SendReactionRequest(
            peer=chat,
            msg_id=message_id,
            big=True,
            add_to_recent=True,
            reaction=[reaction]
        ))

    async def send_react_emoticon(self,
                                  chat: InputPeerEmpty | InputPeerSelf | InputPeerChat | InputPeerUser | InputPeerChannel | InputPeerUserFromMessage | InputPeerChannelFromMessage,
                                  message_id: int, emoticon: str):
        await self.send_react(chat, message_id, types.ReactionEmoji(emoticon=emoticon))

    async def get_reactions(self,
                            chat: InputPeerEmpty | InputPeerSelf | InputPeerChat | InputPeerUser | InputPeerChannel | InputPeerUserFromMessage | InputPeerChannelFromMessage,
                            message_id: int) -> MessageReactionsList:
        return await self(functions.messages.GetMessageReactionsListRequest(
            peer=chat,
            id=message_id,
            limit=100
        ))

    async def _dispatch_update(self: 'KitikiClient', update):
        # TODO only used for AlbumHack, and MessageBox is not really designed for this
        others = None

        if not self._mb_entity_cache.self_id:
            # Some updates require our own ID, so we must make sure
            # that the event builder has offline access to it. Calling
            # `get_me()` will cache it under `self._mb_entity_cache`.
            #
            # It will return `None` if we haven't logged in yet which is
            # fine, we will just retry next time anyway.
            try:
                await self.get_me(input_peer=True)
            except OSError:
                pass  # might not have connection

        built = EventBuilderDict(self, update, others)
        for conv_set in self._conversations.values():
            for conv in conv_set:
                ev = built[events.NewMessage]
                if ev:
                    conv._on_new_message(ev)

                ev = built[events.MessageEdited]
                if ev:
                    conv._on_edit(ev)

                ev = built[events.MessageRead]
                if ev:
                    conv._on_read(ev)

                if conv._custom:
                    await conv._check_custom(built)

        for builder, callback, plugin in self._event_builders:
            event = built[type(builder)]
            if not event:
                continue

            if not builder.resolved:
                await builder.resolve(self)

            filter = builder.filter(event)
            if inspect.isawaitable(filter):
                filter = await filter
            if not filter:
                continue

            try:
                if plugin:
                    await callback(self, event)
                else:
                    await callback(event)
            except errors.AlreadyInConversationError:
                name = getattr(callback, '__name__', repr(callback))
                self._log[__name__].debug(
                    'Event handler "%s" already has an open conversation, '
                    'ignoring new one', name)
            except events.StopPropagation:
                name = getattr(callback, '__name__', repr(callback))
                self._log[__name__].debug(
                    'Event handler "%s" stopped chain of propagation '
                    'for event %s.', name, type(event).__name__
                )
                break
            except Exception as e:
                if not isinstance(e, asyncio.CancelledError) or self.is_connected():
                    name = getattr(callback, '__name__', repr(callback))
                    self._log[__name__].exception('Unhandled exception on %s', name)

    async def _dispatch_event(self: 'KitikiClient', event):
        """
        Dispatches a single, out-of-order event. Used by `AlbumHack`.
        """
        # We're duplicating a most logic from `_dispatch_update`, but all in
        # the name of speed; we don't want to make it worse for all updates
        # just because albums may need it.
        for builder, callback, plugin in self._event_builders:
            if isinstance(builder, events.Raw):
                continue
            if not isinstance(event, builder.Event):
                continue

            if not builder.resolved:
                await builder.resolve(self)

            filter = builder.filter(event)
            if inspect.isawaitable(filter):
                filter = await filter
            if not filter:
                continue

            try:
                if plugin:
                    await callback(self, event)
                else:
                    await callback(event)
            except errors.AlreadyInConversationError:
                name = getattr(callback, '__name__', repr(callback))
                self._log[__name__].debug(
                    'Event handler "%s" already has an open conversation, '
                    'ignoring new one', name)
            except events.StopPropagation:
                name = getattr(callback, '__name__', repr(callback))
                self._log[__name__].debug(
                    'Event handler "%s" stopped chain of propagation '
                    'for event %s.', name, type(event).__name__
                )
                break
            except Exception as e:
                if not isinstance(e, asyncio.CancelledError) or self.is_connected():
                    name = getattr(callback, '__name__', repr(callback))
                    self._log[__name__].exception('Unhandled exception on %s', name)
