import random

import bot
import command


class RouletteHandler(command.CommandHandler):
    def run_roulette(self, message: bot.Message, points: int) -> str:
        if random.randint(0, 1):
            return message.username + " won " + str(points) + " points!"
        else:
            return message.username + " lost " + str(points) + " points!"