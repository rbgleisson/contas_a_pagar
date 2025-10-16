# core/__init__.py — inicializa schema/migração ao importar o pacote
from .database import init_schema, migrate_schema_if_needed

init_schema()
migrate_schema_if_needed()
