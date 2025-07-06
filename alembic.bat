@echo off

set /P comment="Comment: "
python -m alembic revision --autogenerate -m "%comment%"