from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed historical/static wetlands into the database so they can be monitored."

    def handle(self, *args, **options):
        from mapping.views import _seed_static_wetlands_into_db

        created_count = _seed_static_wetlands_into_db()

        if created_count:
            self.stdout.write(self.style.SUCCESS(f"Created {created_count} historical wetlands."))
        else:
            self.stdout.write(self.style.WARNING("No new historical wetlands were created."))
