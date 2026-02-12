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

        if not password:
            self.stdout.write('DJANGO_ADMIN_PASSWORD not set, skipping admin creation.')
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': True, 'is_superuser': True},
        )

        # Always set the password (handles both new and existing users)
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f'Admin user "{username}" created successfully.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Admin user "{username}" password updated.'))
