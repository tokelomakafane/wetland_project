from django.conf import settings
from django.core.management.base import BaseCommand

import ee


class Command(BaseCommand):
    help = "Authenticate Earth Engine using the browser-based notebook flow and verify initialization."

    def add_arguments(self, parser):
        parser.add_argument(
            '--auth-mode',
            default='notebook',
            choices=['notebook', 'localhost', 'gcloud', 'gcloud-legacy', 'colab', 'appdefault'],
            help='Earth Engine authorization mode to use.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-authentication even if cached credentials already exist.',
        )

    def handle(self, *args, **options):
        auth_mode = options['auth_mode']
        force = options['force']
        project = getattr(settings, 'EE_PROJECT', None)

        self.stdout.write(f'Authenticating Earth Engine with auth_mode={auth_mode!r}...')
        result = ee.Authenticate(auth_mode=auth_mode, force=force)

        if result is True and not force:
            self.stdout.write(self.style.SUCCESS('Existing Earth Engine credentials are valid.'))
        else:
            self.stdout.write(self.style.SUCCESS('Saved Earth Engine authorization token.'))

        ee.Initialize(project=project)
        self.stdout.write(self.style.SUCCESS('Earth Engine initialization succeeded.'))