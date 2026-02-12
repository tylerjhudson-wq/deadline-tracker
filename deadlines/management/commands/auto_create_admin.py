"""
Automatically create or update admin superuser from environment variables.
Uses DJANGO_ADMIN_USERNAME and DJANGO_ADMIN_PASSWORD env vars.
"""

import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Create or update admin superuser from environment variables'

    def handle(self, *args, **options):
        username = os.getenv('DJANGO_ADMIN_USERNAME', 'admin')
        password = os.getenv('DJANGO_ADMIN_PASSWORD', '')
        email = os.getenv('DJANGO_ADMIN_EMAIL', 'admin@firm.com')

        self.stdout.write(f'Admin setup: username="{username}", password length={len(password)}, email="{email}"')

        if not password:
            self.stdout.write('DJANGO_ADMIN_PASSWORD not set, skipping admin creation.')
            return

        # Delete all existing users and start fresh
        User.objects.all().delete()
        self.stdout.write('Cleared all existing users.')

        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Admin user "{username}" created. is_staff={user.is_staff}, is_superuser={user.is_superuser}, has_usable_password={user.has_usable_password()}'
        ))
