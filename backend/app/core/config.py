from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    DEBUG: bool = False
    SECRET_KEY: str = "changeme"
    ENCRYPTION_KEY: str = ""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://porubly:porubly@localhost:5432/porubly"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT (RS256)
    JWT_PRIVATE_KEY_PATH: str = "keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str = "keys/public.pem"
    JWT_AUDIENCE: str = "porubly-api"
    JWT_ISSUER: str = "porubly"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS_ANONYMOUS: int = 180

    # Donations
    DONATION_COOLDOWN_HOURS: int = 8

    # CORS
    CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # S3 / MinIO
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "porubly"
    S3_PUBLIC_URL: str = "http://localhost:8000/media"

    # Payment
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""

    # Notifications
    NOTIFICATION_PROVIDER: str = "mock"  # mock | firebase
    FIREBASE_CREDENTIALS_PATH: str = ""  # path to service account JSON

    # Email (OTP)
    EMAIL_PROVIDER: str = "mock"  # mock | sendgrid | smtp
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SENDGRID_API_KEY: str = ""

    # Domains
    API_DOMAIN: str = "localhost"
    PUBLIC_API_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


def build_media_url(s3_key: str) -> str:
    """Build a public URL for an S3 object from its key."""
    return f"{settings.S3_PUBLIC_URL.rstrip('/')}/{s3_key}"
