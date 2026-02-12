"""
Automatically create an admin superuser if one doesn't exist.
Uses DJANGO_ADMIN_USERNAME and DJANGO_ADMIN_PASSWORD env vars.
"""

import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Create admin superuser from environment variables if none exists'

    def handle(self, *args, **options):
        username = os.getenv('DJANGO_ADMIN_USERNAME', 'admin')
        password = os.getenv('DJANGO_ADMIN_PASSWORD', '')
        email = os.getenv('DJANGO_ADMIN_EMAIL', 'admin@firm.com')

        if not password:
            self.stdout.write('DJANGO_ADMIN_PASSWORD not set, skipping admin creation.')
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Admin user "{username}" already exists, skipping.')
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f'Admin user "{username}" created successfully.'))
