import random

import base
import command


class RouletteHandler(command.CommandHandler):
    def run_roulette(self, message: base.Message, points: int) -> str:
        starting_points = int(self.data.get(message.user.name, "0"))
        if starting_points < points:
            if not starting_points:
                raise base.UserError("You don't have any points!")
            elif starting_points == 1:
                raise base.UserError("You only have 1 point.")
            raise base.UserError(f"You only have {starting_points} points.")
        if random.randint(0, 1):
            new_points = starting_points + points
            self.data.set(message.user.name, str(new_points))
            return (f"{message.user} won {points} points and now has "
                    f"{new_points} points!")
        else:
            new_points = starting_points - points
            self.data.set(message.user.name, str(new_points))
            return (f"{message.user} lost {points} points and now has "
                    f"{new_points} points.")
