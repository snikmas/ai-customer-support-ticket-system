from datetime import datetime
# KEYS: KEY NAMES ONLY

#   rate limiting
#      caching
#      temporary session/token data
#      background AI job queue later
#      pub/sub later if needed

def build_login_attempt_key(identifier: str) -> str:
    normalized_identifier = identifier.strip().lower()

    if '@' in normalized_identifier:
        identifier_type = 'email'
    else: identifier_type = 'nickname'

    return f"login_attempts:{identifier_type}:{normalized_identifier}"
