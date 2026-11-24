"""Convert database values into JSON-safe structures."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import inspect as sa_inspect


def jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "__table__"):
        return {attr.key: jsonable(getattr(value, attr.key)) for attr in sa_inspect(value).mapper.column_attrs}
    return value
