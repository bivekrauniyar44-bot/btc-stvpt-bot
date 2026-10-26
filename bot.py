
class PaperBot:
    def __init__(self):
        self.position = None
        self.entry_price = None
        self.stake = 1
        self.loss_streak = 0
        self.max_stake = 4
        self.log = []

    def process_signal(self, main_color, fast_color, price):
        main_color = main_color.lower()
        fast_color = fast_color.lower()
        action = "WAIT"

        if main_color not in ("green", "red"):
            return "WAIT: invalid main signal"

        if fast_color not in ("green", "red"):
            return "WAIT: invalid stop signal"

        if self.position is None:
            # Enter only when both indicators agree.
            if main_color == "green" and fast_color == "green":
                self.position = "BUY"
                self.entry_price = float(price)
                action = "PAPER BUY"
            elif main_color == "red" and fast_color == "red":
                self.position = "SELL"
                self.entry_price = float(price)
                action = "PAPER SELL"
        else:
            # The faster indicator changing color closes the paper position.
            stop_hit = (
                (self.position == "BUY" and fast_color == "red")
                or (self.position == "SELL" and fast_color == "green")
            )

            if stop_hit:
                self.log.append({
                    "position": self.position,
                    "entry": self.entry_price,
                    "exit": float(price),
                    "stake": self.stake,
                    "result": "CLOSED - P&L not yet calculated"
                })
                self.position = None
                self.entry_price = None
                action = "PAPER CLOSE"

        return action

    def record_result(self, won):
        # Call only after a paper trade has actually been evaluated.
        if won:
            self.loss_streak = 0
            self.stake = 1
        else:
            self.loss_streak += 1
            if self.loss_streak % 3 == 0:
                self.stake = min(self.stake + 1, self.max_stake)

    def status(self):
        return {
            "mode": "PAPER ONLY",
            "position": self.position or "NONE",
            "entry_price": self.entry_price,
            "stake": self.stake,
            "loss_streak": self.loss_streak,
            "max_stake": self.max_stake,
            "closed_trades": len(self.log)
        }
