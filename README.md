## Impbot

Impbot is a chat bot framework! Out of the box, it's a lightly featured bot for Twitch streams,
offering custom command responses configurable by moderators, with more features on the way. As a
framework, its goal is to make it quick and easy to customize your bot with any functionality you
like -- as simple as a custom chat response, or as powerful as a remote API connection -- by dashing
off a little bit of Python.

Impbot is self-hosted: Your bot runs on your own computer or private server, and connects to Twitch
using its own Twitch account, appearing in chat with the username of your choice.

It's not just for Twitch: a single Impbot instance can connect to multiple chat services
simultaneously, sharing the same features and data across all of them if you like, so your community
can enjoy the same friendly robotic presence on-stream in your Twitch chat and off-stream in, for
example, your Discord server. (Discord support is coming soon.)

### Status

Impbot is a work in progress, and is definitely not yet v1.0. That means even the core APIs might
change without warning, and some useful features aren't implemented yet. That said, it's already in
active use in some smaller stream communities.

* [TwoHeadedGiant](https://twitch.tv/TwoHeadedGiant) uses an Impbot chat command to let viewers
  change the colors of the Hue smart lights in the room behind him on camera. An Impbot event
  handler flashes the lights every time there's a new subscriber.
* [Ms. Boogie](https://twitch.tv/ms_boogie) loaded her Impbot database with bat facts, and
  the `!batfact` command supplies a new one each time.

Until shared infrastructure is in place to handle authentication, running an Impbot instance
requires first [registering a new Twitch API application](https://dev.twitch.tv/console/apps/create)
to obtain a client ID and client secret.

### Scripting

See [scripting.md](docs/scripting.md) for an overview of Impbot's major abstractions, and a guide to
adding new features to your bot.