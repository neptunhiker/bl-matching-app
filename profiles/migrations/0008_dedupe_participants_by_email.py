from django.db import migrations


def dedupe_participants_by_normalized_email(apps, schema_editor):
    Participant = apps.get_model("profiles", "Participant")
    db_alias = schema_editor.connection.alias

    seen_by_email = set()
    duplicate_ids = []

    # Keep oldest participant per normalized email.
    participants = (
        Participant.objects.using(db_alias)
        .all()
        .order_by("created_at", "id")
        .values_list("id", "email")
    )

    for participant_id, email in participants.iterator():
        normalized_email = (email or "").strip().lower()
        if not normalized_email:
            continue

        if normalized_email in seen_by_email:
            duplicate_ids.append(participant_id)
            continue

        seen_by_email.add(normalized_email)

    if duplicate_ids:
        Participant.objects.using(db_alias).filter(id__in=duplicate_ids).delete()


def noop_reverse(apps, schema_editor):
    # Data deletions are not reversible.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0007_participant_notes"),
    ]

    operations = [
        migrations.RunPython(dedupe_participants_by_normalized_email, noop_reverse),
    ]
