from django.db import migrations


def fix_communityinput_schema(apps, schema_editor):
    table = 'mapping_communityinput'

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [row[1] for row in cursor.fetchall()]

        if 'observation_category' in columns and 'observation' not in columns:
            cursor.execute(
                f"ALTER TABLE {table} RENAME COLUMN observation_category TO observation;"
            )

        if 'updated_at' not in columns:
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN updated_at datetime NOT NULL DEFAULT '1970-01-01 00:00:00';"
            )
            cursor.execute(
                f"UPDATE {table} SET updated_at = created_at WHERE updated_at = '1970-01-01 00:00:00';"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0004_communityinput'),
    ]

    operations = [
        migrations.RunPython(fix_communityinput_schema, migrations.RunPython.noop),
    ]
