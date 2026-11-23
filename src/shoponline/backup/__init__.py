"""Encrypted backups of the database and the application data, kept on this machine and on
Google Drive, with restore and machine migration built on the same archives."""

KINDS = ("db", "app", "full")
KIND_LABELS = {"db": "Database", "app": "Ứng dụng", "full": "Toàn bộ"}
