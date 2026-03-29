from django.conf import settings

def environment_context(request):
    return {
        "ENVIRONMENT": settings.ENVIRONMENT,
        "IS_STAGING": settings.ENVIRONMENT == "staging",
        "IS_PRODUCTION": settings.ENVIRONMENT == "production",
    }