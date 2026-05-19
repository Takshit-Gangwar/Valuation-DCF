import json
import os

PORTFOLIO_FILE = 'watchlist.json'


class Portfolio:
    def __init__(self):
        self.entries = []
        self.load()

    def load(self):
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE) as f:
                    self.entries = json.load(f)
            except Exception:
                self.entries = []

    def save(self):
        with open(PORTFOLIO_FILE, 'w') as f:
            json.dump(self.entries, f, indent=2)

    def add(self, ticker):
        ticker = ticker.upper()
        if not any(e['ticker'] == ticker for e in self.entries):
            self.entries.append({'ticker': ticker})
            self.save()

    def remove(self, ticker):
        self.entries = [e for e in self.entries if e['ticker'] != ticker.upper()]
        self.save()

    def tickers(self):
        return [e['ticker'] for e in self.entries]
