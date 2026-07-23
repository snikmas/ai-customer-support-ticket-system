from datetime import datetime
# KEYS: KEY NAMES ONLY

# rate limiting
# caching
# temporary session/token data
# background AI job queue later
# pub/sub later if needed

def build_login_attempt_key(identifier: str) -> str:
    normalized_identifier = identifier.strip().lower()

    if '@' in normalized_identifier:
        identifier_type = 'email'
    else: identifier_type = 'nickname'

    return f"login_attempts:{identifier_type}:{normalized_identifier}"

def build_analysis_rate_limit_key(user_id: str) -> str:
    return f"analysis_rate_limit:user:{user_id.strip().lower()}"

def build_ticket_key(ticket_id: str) -> str:
    normalized_ticket_id = ticket_id.strip().lower()
    return f"ticket:{ticket_id}"
