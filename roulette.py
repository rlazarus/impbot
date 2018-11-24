import random

import bot
import command
import data


class RouletteHandler(command.CommandHandler):
    def run_roulette(self, message: bot.Message, points: int) -> str:
        starting_points = int(data.get(self, message.username, "0"))
        if starting_points < points:
            if not starting_points:
                raise bot.UserError("You don't have any points!")
            elif starting_points == 1:
                raise bot.UserError("You only have 1 point.")
            raise bot.UserError(f"You only have {starting_points} points.")
        if random.randint(0, 1):
            new_points = starting_points + points
            data.set(self, message.username, str(new_points))
            return (f"{message.username} won {points} points and now has "
                    f"{new_points} points!")
        else:
            new_points = starting_points - points
            data.set(self, message.username, str(new_points))
            return (f"{message.username} lost {points} points and now has "
                    f"{new_points} points.")
