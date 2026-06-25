from enum import Enum

class Status(Enum):
    NEW = 'New'
    OPEN = 'Open'
    PENDING = 'Pending'
    IN_PROGRESS = 'In progress'
    ON_HOLD = 'On hold'
    RESOLVED = 'Resolved'
    CLOSED = 'Closed'
    REOPENED =      'Reopened'

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
  CRITICAL = 'critical',
  HIGH = 'high',
  NORMAL = 'normal',
  LOW = 'low'
