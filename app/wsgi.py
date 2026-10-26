"""Gunicorn / flask entry point."""
from dotenv import load_dotenv

load_dotenv()

from manasety import create_app  # noqa: E402

app = create_app()
