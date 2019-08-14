This is intended as a guide for anyone interested in adding custom functionality
to Impbot by writing a little Python. It introduces the major abstractions of
the framework and walks you through how to use them.

A primary goal of Impbot is that it should be quick and easy to add modular 
features to your own bot, using minimal boilerplate and without needing to dig
into the core workings of the bot.

## Handlers

A **handler** reacts to **events**, including incoming messages. In general,
you'll implement a bot's main user-visible features by writing handlers.

Each handler processes each event in two stages. First, every handler's `check`
method is called, one at a time. The handler inspects the event and decides
whether it wants to react; if so, it returns `True`. Only one handler can accept
each event, so as soon as any handler returns `True` from its `check` method, no
other handlers' `check` methods are called.

Second, if any handler returned `True` from its `check` method, that handler's
`run` method is called with the same event. Here the handler takes whatever
action was triggered by the event. If it returns a string, it's sent as a reply
to the incoming message. (The `run` method can also return `None`, meaning that
no reply is sent, but the event is still considered handled -- it won't be
offered to any other handlers.)

Here's an example of a handler that responds to any message that says (exactly)
"hello, impbot" with the reply "Hello, world!"

```python
class HelloHandler(base.Handler):
    def check(self, message: base.Message) -> bool:
        return message.text == "hello, impbot"

    def run(self, message: base.Message) -> str:
        return "Hello, world!"
```

In this example, the `check` method rejects any message that isn't exactly the
trigger string we're looking for, so the `run` method doesn't need any
additional logic. If we wanted to greet the user by name instead, the event
object carries the information we'd need:

```python
def run(self, message: base.Message) -> str:
    return f"Hello, {message.user}!"
```

## Command handlers

A common idiom is for chat bots to respond to **commands** that start with a
punctuation prefix, conventionally `!` on Twitch. A **command handler** is a
particular kind of handler designed to make this easy. In order for our handler
to respond to `!hello`, we'd write it like this:

```python
class MyHandler(command.CommandHandler):
    def run_hello(self) -> str:
        return "Hello, world!"
```

The command name is taken from the method name: since the method is named
`run_hello`, it's triggered by the command `!hello`, and we don't write a
`check`. The name of the class doesn't matter, just the method -- and a
CommandHandler can have any number of different command methods.

(That's just an example -- if your command only needs to respond with a static
message, you can use the built-in CustomCommandHandler and add it with `!addcom`
instead of writing any code.)

With a CommandHandler, we can add **arguments** to the command simply by adding
them to our method. For example, the bot can reply to the command `!greet Frank`
with "Howdy, Frank!" like this:

```python
class GreetingHandler(command.CommandHandler):
    def run_greet(self, name: str) -> str:
        return f"Howdy, {name}!"
```

Arguments don't have to be strings: they'll be automatically converted according
to the [type hint](https://docs.python.org/3/library/typing.html). For a
gambling command, players might have to bet a certain number of points, like
`!gamble 50`, and that argument should be treated as an integer. So the handler
might start out like this:

```python
class GamblingHandler(command.CommandHandler):
    def run_gamble(self, wager: int) -> str:
        # ...
```

If your method has more than one argument, they'll be parsed from the input by
splitting on spaces. If the _last_ argument is a string, it gets the entire
remaining input, so it may be more than one word. As a special case, if there
are no arguments, any text after the command is ignored.

Arguments may be **optional**, with type hints like `Optional[int]`. If the
optional arguments are left out of the command, they'll be passed as `None`. All
the required arguments must come first, then all optional ones. (It doesn't
matter whether they're also "optional" in the sense of having a default argument
-- that is, either `name: Optional[str]` or `name: Optional[str] = None` is 
fine. The default argument, if present, is ignored.) 

When a user tries to use a command with the wrong number or type of arguments,
your `run_` method won't be called at all, and instead they'll get an
automatically-generated message explaining how to use the command -- in the case
above, it would say `Usage: !gamble <wager>`. You can override this usage
message by setting a docstring on your `run_` method.

If this parsing doesn't suit you, you can do it yourself: just give your method
a single `str` argument, and it'll receive everything after the command, so you
can split up the text any way you like.

Optionally, you can include an argument of type `base.Message` _before_ any
arguments to the command. If you do, you'll have access to the message event,
most commonly so that you can get the user's name.

```python
class GamblingHandler(command.CommandHandler):
    def run_gamble(self, message: base.Message, wager: int) -> str:
        # ...
        if winner:
            return f"{message.user} won {wager} points!"
        # ...
```

Normally, type hints are optional in Python. Impbot relies on them for critical
information, so they're _required_ -- if you leave them out, your bot will fail
to start up. This behavior can be a little surprising: at first glance, it may
feel uncomfortably magical for your method to be called with different arguments
depending on your type hints. The benefit is that it allows you to write your
handler without a lot of extra boilerplate declaring how to call it: the type
hints are all you need.

Remember, this type detection only happens for command handlers -- plain old
`Handler` subclasses just have an ordinary `check` and `run` method, and each
takes an `Event`.

## Data

The bot incorporates an SQLite database for persisting data -- for example, the
`GamblingHandler` above might use this for keeping track of each user's score,
and might add and subtract points when they win and lose.

By default, each handler has access to its own data, isolated from other
handlers. This is called a **namespace**. (The namespace name is based on the
unqualified name of the handler class, so avoid giving two handler classes the
same name; their data would be merged.) The namespace provides a
string-key-string-value interface to the underlying table, so a handler might
say `self.data.set("name", "impbot")`, and then subsequent calls to
`self.data.get("name")` would return `"impbot"` -- but only in the same handler.

For now, calling methods on the namespace from a handler's `__init__` method
will raise an error, as the database hasn't been initialized at that phase of
the bot's startup. This might change in the future.

## Connections

A **connection** is how your bot sends and receives messages on a chat service
like Twitch or Discord. You may not need to write one -- if a connection for
your chat service is built-in, you can just use it, initializing it with your
OAuth token or other credentials.

If you do need a custom connection, subclass `base.Connection` and implement
three methods:

`run(self, on_event: Callable[[base.Event], None]) -> None` -- This should
connect to your chat service as the bot and handle input indefinitely. Every
time the bot receives a message, construct a `base.Message` event and call the
supplied callback with it. (For other events, you might pass your own subclass
of `base.Event`.) You can call the callback directly: the event is queued for
handling on another thread, and the callback will return immediately, without
waiting for handling to finish. Return from `run` when you're ready for the bot
to exit.

`say(self, text: str) -> None` -- This should send a message as the bot, where
`text` is the message to be sent to your chat service.

`shutdown(self) -> None` -- This is your signal that the bot is exiting. It
should close the connection to your chat server. If necessary, send a signal to
your `run` method (which is running on a different thread) to break out of any
loops and return. Handlers won't receive any events passed to the callback after
this point.

Like handlers, connections (or utility classes) may also want data persistence,
for example to store OAuth tokens. They aren't constructed with a namespace by
default, but can simply instantiate one with `data.Namespace("MyClassName")`.
(This can be done in the connection's `__init__` -- but don't call any _methods_
on the namespace yet, as described with handlers above.) Note that the
`Namespace` object wraps a `sqlite3.Connection` under the hood, so sharing an
instance between threads will raise concurrency errors.

## Threading

Impbot's threading model is designed so that you won't have to worry about
threads when writing a connection or handler: you can treat each as
single-threaded.

Under the hood, Impbot's threads run in an event producer/consumer arrangement.
Each connection is started in its own thread, and freely handles its own pings
or keepalives as necessary. All the connections construct event objects and
buffer them onto a single FIFO event queue.

All events are handled one after another, on a single thread, regardless of what
connection they came from. That means individual handlers don't have to be
thread-safe, which makes it much simpler to write handlers that need to keep any
internal state between inputs. It also means handlers can safely keep state
between `check` and `run` for the _same_ input -- for example, if you need to
match against a regular expression in `check` and use values from its capturing
groups in `run`, you don't need to execute the regex twice: you can store the
values in a field during `check` and retrieve them during `run`. That maneuver
is safe because there's only a single event-handling thread.

But it also means that any handler that does blocking work can freeze up the
bot: the connections won't time out and will continue queueing new events, but
no handlers can run until the slow one finishes, so those events will stack up
unanswered. To avoid this problem, handlers with slow work to do (such as
sleeping, or making API calls to other services) should spin off their own
long-lived threads and return promptly from `run`. If you do this, you're
responsible for thread-safe handling of your own shared data.
