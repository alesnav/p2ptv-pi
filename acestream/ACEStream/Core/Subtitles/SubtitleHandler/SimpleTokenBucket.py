#Embedded file name: ACEStream\Core\Subtitles\SubtitleHandler\SimpleTokenBucket.pyo
from time import time

class SimpleTokenBucket(object):

    def __init__(self, fill_rate, capacity = -1):
        if capacity == -1:
            capacity = 1073741824
        self.capacity = float(capacity)
        self._tokens = float(0)
        self.fill_rate = float(fill_rate)
        self.timestamp = time()

    def consume(self, tokens):
        if tokens <= self.tokens:
            self._tokens -= tokens
        else:
            return False
        return True

    def _consume_all(self):
        self._tokens = float(0)

    @property
    def tokens(self):
        if self._tokens < self.capacity:
            now = time()
            delta = self.fill_rate * (now - self.timestamp)
            self._tokens = min(self.capacity, self._tokens + delta)
            self.timestamp = now
        return self._tokens

    @property
    def upload_rate(self):
        return self.fill_rate
