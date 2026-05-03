from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0008_dedupe_participants_by_email"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="participant",
            constraint=models.UniqueConstraint(
                Lower("email"),
                name="profiles_participant_email_ci_unique",
            ),
        ),
    ]
