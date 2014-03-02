#Embedded file name: ACEStream\Core\exceptions.pyo


class ACEStreamException(Exception):

    def __init__(self, msg = None):
        Exception.__init__(self, msg)

    def __str__(self):
        return str(self.__class__) + ': ' + Exception.__str__(self)


class OperationNotPossibleAtRuntimeException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)


class OperationNotPossibleWhenStoppedException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)


class OperationNotEnabledByConfigurationException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)


class NotYetImplementedException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)


class DuplicateDownloadException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)


class VODNoFileSelectedInMultifileTorrentException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)


class LiveTorrentRequiresUsercallbackException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)


class TorrentDefNotFinalizedException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)


class ACEStreamLegacyException(ACEStreamException):

    def __init__(self, msg = None):
        ACEStreamException.__init__(self, msg)
