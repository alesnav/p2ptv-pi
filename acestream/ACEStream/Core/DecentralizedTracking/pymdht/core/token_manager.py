#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\token_manager.pyo


class TokenManager(object):

    def __init__(self):
        self.current_token = '123'

    def get(self):
        return self.current_token

    def check(self, token):
        return token == self.current_token
