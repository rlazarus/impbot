import random

import bot
import command


class RouletteHandler(command.CommandHandler):
    def run_roulette(self, message: bot.Message, points: str) -> str:
        try:
            points = int(points)
        except ValueError:
            raise bot.UserError
        if random.randint(0, 1):
            return message.username + " won " + str(points) + " points!"
        else:
            return message.username + " lost " + str(points) + " points!"