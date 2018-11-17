import random

import bot
import command


class RouletteHandler(command.CommandHandler):
    def run_roulette(self, message: bot.Message, points: int) -> str:
        if random.randint(0, 1):
            return f"{message.username} won {points} points!"
        else:
            return f"{message.username} lost {points} points!"
