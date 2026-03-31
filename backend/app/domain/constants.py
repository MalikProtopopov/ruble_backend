"""Business constants — single source of truth."""

# Payment
PLATFORM_FEE_PERCENT = 15

# Subscriptions
ALLOWED_SUBSCRIPTION_AMOUNTS = frozenset({100, 300, 500, 1000})  # kopecks per day
BILLING_PERIOD_MULTIPLIER = {"weekly": 7, "monthly": 30}
MAX_ACTIVE_SUBSCRIPTIONS = 5

# Donations
MIN_DONATION_AMOUNT_KOPECKS = 1000  # 10 rub

# Auth / OTP
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RATE_LIMIT_SECONDS = 60

# JWT
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Media
MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024   # 500 MB
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_AUDIO_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_VIDEO_CONTENT_TYPES = frozenset({"video/mp4"})
ALLOWED_DOCUMENT_CONTENT_TYPES = frozenset({"application/pdf"})
ALLOWED_AUDIO_CONTENT_TYPES = frozenset(
    {"audio/mpeg", "audio/mp4", "audio/ogg", "audio/webm"}
)
ALLOWED_IMAGE_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}
)

# Patron
PATRON_LINK_TTL_HOURS = 24

# Retry schedule (days) for soft decline
SOFT_DECLINE_RETRY_DAYS = (1, 3, 7, 14)
