class RipeSyncException(Exception):
    pass


class PrefixTooSmall(RipeSyncException):
    pass


class NotRoutablePrefix(RipeSyncException):
    pass


class TemplateNotFound(RipeSyncException):
    pass


class RipeAPIError(RipeSyncException):
    pass


class MissingConfig(RipeSyncException):
    pass


class OverlapConflict(RipeSyncException):
    pass
