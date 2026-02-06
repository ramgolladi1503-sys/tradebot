class FakeKiteClient:
    def __init__(self):
        self.kite = object()  # mimic logged-in client
        self._trades = []
        self._resolve_tokens = {}
        self.raise_on_trades = False
        self.raise_on_quote = False
        self.quote_payload = {}
        self.ltp_payload = {}

    def trades(self):
        if self.raise_on_trades:
            raise RuntimeError("Kite rate limited")
        return list(self._trades)

    def set_trades(self, trades):
        self._trades = trades

    def resolve_tokens(self, symbols, exchange="NFO"):
        out = []
        for s in symbols:
            tok = self._resolve_tokens.get((exchange, s))
            if tok is not None:
                out.append(tok)
        return out

    def set_token(self, exchange, symbol, token):
        self._resolve_tokens[(exchange, symbol)] = token

    def quote(self, symbols):
        if self.raise_on_quote:
            raise RuntimeError("Kite quote failure")
        return self.quote_payload

    def ltp(self, symbols):
        return self.ltp_payload
