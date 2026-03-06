import pytest
from django.core import mail


@pytest.fixture(autouse=True)
def use_anymail_test_backend(settings):
    """
    Override the email backend for every test in the project.

    - Prevents any real HTTP calls to the Brevo API.
    - anymail.test.EmailBackend populates django.core.mail.outbox with
      AnymailMessage instances, so tests can inspect .tags, .to, .bcc, etc.
    - mail.outbox is reset to [] before each test so outbox state never leaks
      between tests.
    - The settings fixture from pytest-django scopes all overrides to the
      current test; they are reverted automatically after each test.
    """
    settings.EMAIL_BACKEND = 'anymail.backends.test.EmailBackend'
    settings.ANYMAIL = {'BREVO_API_KEY': 'test-key'}
    mail.outbox = []
