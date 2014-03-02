#Embedded file name: ACEStream\Core\Base.pyo
from ACEStream.Core.exceptions import *
DEBUG = False

class Serializable:

    def __init__(self):
        pass


class Copyable:

    def copy(self):
        raise NotYetImplementedException()
