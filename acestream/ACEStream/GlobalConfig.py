#Embedded file name: ACEStream\GlobalConfig.pyo


class GlobalConfig:

    def __init__(self):
        self.config = {}

    def set_mode(self, mode):
        self.set_value('_mode', mode)

    def get_mode(self):
        return self.get_value('_mode')

    def set_value(self, name, value):
        self.config[name] = value

    def get_value(self, name, default = None):
        return self.config.get(name, default)


globalConfig = GlobalConfig()
