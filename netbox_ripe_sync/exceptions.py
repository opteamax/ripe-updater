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


class ResourceMembershipError(RipeSyncException):
    """Raised when a prefix is not within any RIPE My Resources allocation/assignment."""
    pass
