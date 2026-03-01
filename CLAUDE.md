# Project Rules

## Alembic Migrations

- NEVER manually create or hand-write Alembic migration files. Always use `alembic revision --autogenerate -m "description"` to generate migrations.
- ALWAYS confirm with the user that the application is not running before generating or applying migrations. Alembic and the running app can conflict on the database connection.
