import json
import time
import hmac
import hashlib

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from matching.models import RequestToCoach


def _verify_slack_request(request):
    """
    Verify Slack request using signing secret.
    Prevents forged requests.
    """

    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    slack_signature = request.headers.get("X-Slack-Signature")

    if not timestamp or not slack_signature:
        return False

    # prevent replay attacks
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False

    body = request.body.decode("utf-8")

    sig_basestring = f"v0:{timestamp}:{body}"

    my_signature = (
        "v0="
        + hmac.new(
            settings.SLACK_SIGNING_SECRET.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(my_signature, slack_signature)

@csrf_exempt
def slack_interactions(request):

    if not _verify_slack_request(request):
        return HttpResponseForbidden("Invalid Slack signature")

    payload = json.loads(request.POST["payload"])

    action = payload["actions"][0]["action_id"]
    value = payload["actions"][0]["value"]

    rtc = RequestToCoach.objects.get(id=value)

    if action == "accept_request":
        rtc.accept(triggered_by="coach", triggered_by_user=rtc.coach.user)

    elif action == "decline_request":
        rtc.decline(triggered_by="coach", triggered_by_user=rtc.coach.user)

    return HttpResponse(status=200)