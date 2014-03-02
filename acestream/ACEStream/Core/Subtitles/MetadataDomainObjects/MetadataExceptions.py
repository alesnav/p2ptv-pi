#Embedded file name: ACEStream\Core\Subtitles\MetadataDomainObjects\MetadataExceptions.pyo


class RichMetadataException(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class SerializationException(RichMetadataException):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class SignatureException(RichMetadataException):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class MetadataDBException(RichMetadataException):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class SubtitleMsgHandlerException(RichMetadataException):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)
