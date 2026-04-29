from django.core.management.base import BaseCommand
import re
from mapping.models import Wetland

class Command(BaseCommand):
    help = 'Delete demo wetlands named like "Wetland <number>"'

    def handle(self, *args, **options):
        pattern = re.compile(r'(?i)^wetland\s*\d+$')
        all_wetlands = Wetland.objects.all()
        matches = [w for w in all_wetlands if w.name and pattern.match(w.name)]
        self.stdout.write(f'Found {len(matches)} demo wetlands: {[w.id for w in matches]}')
        if matches:
            ids = [w.id for w in matches]
            Wetland.objects.filter(id__in=ids).delete()
            self.stdout.write(f'Deleted {len(ids)} records')
        else:
            self.stdout.write('No demo wetlands found')
        remaining = [w for w in Wetland.objects.all() if w.name and pattern.match(w.name)]
        self.stdout.write(f'Remaining {len(remaining)}')
