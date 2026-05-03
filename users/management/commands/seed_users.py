from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from users.models import UserProfile

DEFAULT_USERS = [
    {
        'username': 'admin',
        'password': 'admin',
        'first_name': 'System',
        'last_name': 'Admin',
        'email': 'admin@wetlands.ls',
        'role': 'system_admin',
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'username': 'doe_officer',
        'password': 'doe123',
        'first_name': 'DOE',
        'last_name': 'Officer',
        'email': 'doe@wetlands.ls',
        'role': 'doe_officer',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'username': 'dma_officer',
        'password': 'dma123',
        'first_name': 'DMA',
        'last_name': 'Officer',
        'email': 'dma@wetlands.ls',
        'role': 'dma_officer',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'username': 'nul_researcher',
        'password': 'nul123',
        'first_name': 'NUL',
        'last_name': 'Researcher',
        'email': 'researcher@nul.ls',
        'role': 'nul_researcher',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'username': 'community',
        'password': 'community123',
        'first_name': 'Community',
        'last_name': 'Member',
        'email': 'community@wetlands.ls',
        'role': 'community_member',
        'is_staff': False,
        'is_superuser': False,
    },
]


class Command(BaseCommand):
    help = 'Seed default user accounts for each role'

    def handle(self, *args, **options):
        for entry in DEFAULT_USERS:
            username = entry['username']
            password = entry['password']
            role = entry['role']

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': entry['first_name'],
                    'last_name': entry['last_name'],
                    'email': entry['email'],
                    'is_staff': entry['is_staff'],
                    'is_superuser': entry['is_superuser'],
                },
            )
            if created:
                user.set_password(password)
                user.save()
                UserProfile.objects.create(user=user, role=role)
                self.stdout.write(self.style.SUCCESS(
                    f'  Created  {username!r}  [{role}]  password={password!r}'
                ))
            else:
                # Ensure profile exists even for pre-existing users
                UserProfile.objects.get_or_create(user=user, defaults={'role': role})
                self.stdout.write(f'  Exists   {username!r}  (skipped)')
