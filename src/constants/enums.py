from enum import Enum

class Status(Enum):
    NEW = 'New'
    OPEN = 'Open'
    PENDING = 'Pending'
    IN_PROGRESS = 'In progress'
    ON_HOLD = 'On hold'
    RESOLVED = 'Resolved'
    CLOSED = 'Closed'
    REOPENED = 'Reopened'

class UserStatus(Enum):
    ACTIVE = 'Active'
    DELETED = 'Deleted'
    BANNED = 'Banned'


class Category(Enum):
    API_ERROR       = "API_Error"
    AUTHENTICATION  = "Authentication"
    MODEL_OUTPUT    = "Model Output"
    RAG_RETRIEVAL   = "Rag Retrieval"
    AGENT_WORKFLOW  = "Agent Workflow"
    PERFORMANCE     = "Perfomance"
    BILLING         = "Billing"
    ACCOUNT_ACCESS  = "Account Access"
    DOCUMENTATION   = "Documentation"
    FEATURE_REQUEST = "Feature Request"

class Tag(Enum):
    API_KEY =       'api-key'
    JWT =           'jwt'
    RATE_LIMIT =    'rate-limit'
    TIMEOUT =       'timeout'
    ERROR_500 =     '500-error'
    ERROR_400 =     '400-error'
    STREAMING =     'streaming'
    CHAT =          'chat'
    EMBEDDINGS =    'embeddings'
    RAG =           'rag'
    VECTOR_SEARCH = 'vector-search'
    FILE_UPLOAD =   'file-upload'
    BAD_ANSWER =    'bad-answer'
    HALLUCINATION = 'hallucination'
    LATENCY =       'latency'
    COST =          'cost'
    USAGE_LIMIT =   'usage-limit'
    PYTHON =        'python'
    JAVASCRIPT =    'javascript'
    FASTAPI =       'fastapi'
    POSTGRES =      'postgres'
    REDIS =         'redis'
    DOCKER =        'docker'
    

class Priority(Enum):
  CRITICAL = 'critical'
  HIGH = 'high'
  NORMAL = 'normal'
  LOW = 'low'

class Role(Enum):
    SUPER_ADMIN = "super_admin"    # Full system access, can manage other admins
    ADMIN = "admin"                # Can manage users, settings, and all tickets
    
    MANAGER = "manager"            # Can assign tickets, manage agents, view reports
    AGENT = "agent"                # Handles tickets, can reply and resolve
    AGENT_READONLY = "agent_readonly"  # Can view tickets but not modify (training)
    
    USER = "user"                  # Regular user - creates and views own tickets
    GUEST = "guest"                # Limited access, can only view public info
    
    BOT = "bot"                    # Automated system user (for webhooks/automation)
    API = "api"                    # API integration user

class EventType(Enum):
    TICKET_CREATED = 'Ticket Created'
    TICKET_CLAIMED = 'Ticket Claimed'
    TICKET_ASSIGNED = 'Ticket Assigned'
    TICKET_REASSIGNED = 'Ticket Reassigned'
    TICKET_DELETED = 'Ticket Deleted'
    TICKETS_BULK_DELETED = 'Tickets Bulk Deleted'
    TICKET_STATUS_CHANGED = 'Ticket Status Changed'
    TICKET_UPDATED = 'Ticket Updated'
    USER_CREATED = 'User Created'
    USER_BULK_DELETED = 'Tickets Bulk Deleted'
    USER_UPDATED = 'User Updated'
    USER_DELETED = 'User Deleted'
    REFRESH_SESSION_CREATED = 'Refresh Session Created'
    REFRESH_SESSION_REVOKED = 'Refresh Session Revoked'
    REFRESH_SESSION_ROTATED = 'Refresh Session Rotated'

class EntityType(Enum):
    TICKET = 'Ticket'
    USER = 'User'
    REFRESH_SESSION = 'Refresh Session'


#   NEW -> due_at = now + 2 hours
#   OPEN -> due_at = now + 6 hours
#   IN_PROGRESS -> due_at = now + 12 hours
#   REOPENED -> due_at = now + 4 hours
#   PENDING / ON_HOLD / RESOLVED / CLOSED -> no due_at change