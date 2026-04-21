"""HTTP API layer (FastAPI). Use `insta_batch.api.app:create_app` as the
uvicorn factory, or `from insta_batch.api.app import create_app` directly.

Kept import-light so tests / tooling can touch this package without forcing
accounts.yaml to exist.
"""
