#Embedded file name: ACEStream\Core\debug.pyo


class DebugState:
    debug_states = {}

    @classmethod
    def get_state(cls, module):
        if module in cls.debug_states:
            return cls.debug_states[module]
        return False

    @classmethod
    def set_state(cls, module, debug):
        cls.debug_states[module] = debug
