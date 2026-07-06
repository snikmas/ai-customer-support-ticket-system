class AppException(Exception):
    status_code = 500  # HTTP 500: unexpected application error
    code = "app_error"
    message = "Application error"

    def __init__(self, message: str | None = None):
        self.message = message or self.message
        super().__init__(self.message)


class BadRequestError(AppException):
    status_code = 400  # HTTP 400: the request shape or value is wrong
    code = "bad_request"
    message = "Bad request"


class AuthenticationError(AppException):
    status_code = 401  # HTTP 401: user is not authenticated
    code = "authentication_error"
    message = "Authentication required"


class InvalidCredentialsError(AuthenticationError):
    status_code = 401  # HTTP 401: login token/password is missing or invalid
    code = "invalid_credentials"
    message = "Invalid credentials"


class AuthorizationError(AppException):
    status_code = 403  # HTTP 403: user is authenticated but has no rights
    code = "authorization_error"
    message = "Permission denied"


class NotFoundError(AppException):
    status_code = 404  # HTTP 404: requested resource does not exist
    code = "not_found"
    message = "Resource not found"


class ConflictError(AppException):
    status_code = 409  # HTTP 409: request conflicts with current resource state
    code = "conflict"
    message = "Resource state conflict"


class GoneError(AppException):
    status_code = 410  # HTTP 410: resource existed before, but is deleted now
    code = "gone"
    message = "Resource is gone"


class InternalOperationError(AppException):
    status_code = 500  # HTTP 500: operation failed even though request was valid
    code = "internal_operation_error"
    message = "Operation failed"


class EmptyUpdateError(BadRequestError):
    status_code = 400  # HTTP 400: PATCH body has no fields to change
    code = "empty_update"
    message = "No update fields provided"


class UserNotFoundError(NotFoundError):
    status_code = 404  # HTTP 404: user id/email/nickname was not found
    code = "user_not_found"
    message = "User not found"


class UserAlreadyExistsError(ConflictError):
    status_code = 409  # HTTP 409: nickname/email/phone is already used
    code = "user_already_exists"
    message = "User already exists"


class InactiveUserError(AuthorizationError):
    status_code = 403  # HTTP 403: deleted/banned user cannot use the system
    code = "inactive_user"
    message = "User is not active"


class TicketNotFoundError(NotFoundError):
    status_code = 404  # HTTP 404: ticket id was not found or is hidden
    code = "ticket_not_found"
    message = "Ticket not found"


class TicketDeletedError(GoneError):
    status_code = 410  # HTTP 410: ticket exists but was soft-deleted
    code = "ticket_deleted"
    message = "Ticket is deleted"


class TicketAlreadyAssignedError(ConflictError):
    status_code = 409  # HTTP 409: ticket already has an assigned agent
    code = "ticket_already_assigned"
    message = "Ticket is already assigned"


class TicketStatusConflictError(ConflictError):
    status_code = 409  # HTTP 409: status transition is not allowed now
    code = "ticket_status_conflict"
    message = "Ticket status does not allow this operation"


class InvalidAssigneeError(BadRequestError):
    status_code = 400  # HTTP 400: chosen assignee is missing or not an agent
    code = "invalid_assignee"
    message = "Invalid assignee"


class CommentNotFoundError(NotFoundError):
    status_code = 404  # HTTP 404: comment id was not found
    code = "comment_not_found"
    message = "Comment not found"


class RefreshSessionNotFoundError(InvalidCredentialsError):
    status_code = 401  # HTTP 401: refresh token/session is invalid
    code = "refresh_session_not_found"
    message = "Invalid refresh session"


class RefreshSessionExpiredError(InvalidCredentialsError):
    status_code = 401  # HTTP 401: refresh session exists but expired
    code = "refresh_session_expired"
    message = "Refresh session expired"


class RefreshSessionRevokedError(InvalidCredentialsError):
    status_code = 401  # HTTP 401: refresh session exists but was logged out
    code = "refresh_session_revoked"
    message = "Refresh session revoked"


class AuditLogError(InternalOperationError):
    status_code = 500  # HTTP 500: main operation or audit event was not saved
    code = "audit_log_error"
    message = "Audit log operation failed"
