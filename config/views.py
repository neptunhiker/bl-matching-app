from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse


def healthcheck(request):
    db_ok = True

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError:
        db_ok = False

    status_code = 200 if db_ok else 503

    return JsonResponse(
        {
            "status": "ok" if db_ok else "error",
            "database": "ok" if db_ok else "unavailable",
        },
        status=status_code,
    )