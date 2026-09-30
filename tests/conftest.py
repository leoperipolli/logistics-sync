import os

# config.Settings exige DATABASE_URL; os testes não acessam banco nem rede.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
