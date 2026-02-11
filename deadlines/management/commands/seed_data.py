"""
Management command to seed deadline types and optionally create sample data.

Usage:
    python manage.py seed_data                  # Seed deadline types only
    python manage.py seed_data --with-samples   # Also create sample matters & deadlines
"""

import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from deadlines.models import Client, Matter, DeadlineType, Deadline


DEADLINE_TYPES = {
    'transaction': [
        'DD Expiration',
        'Extension Election Deadline',
        'Closing Date',
        'Financing Contingency',
        'Title Review Deadline',
        'Survey Deadline',
        'Inspection Deadline',
        'Earnest Money Deadline',
        'Appraisal Deadline',
    ],
    'land_use': [
        'Application Filing Date',
        'Resubmittal Deadline',
        'Hearing Date',
        'Appeal Deadline',
        'Permit Expiration',
        'Public Notice Deadline',
        'Staff Report Due',
        'Neighborhood Meeting',
        'Board/Commission Hearing',
    ],
}

DEFAULT_REMINDER_DAYS = [30, 14, 7, 3, 1]


class Command(BaseCommand):
    help = 'Seed deadline types and optionally create sample data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--with-samples',
            action='store_true',
            help='Also create sample clients, matters, and deadlines',
        )

    def handle(self, *args, **options):
        # Seed deadline types
        created = 0
        for matter_type, type_names in DEADLINE_TYPES.items():
            for name in type_names:
                obj, was_created = DeadlineType.objects.get_or_create(
                    name=name,
                    matter_type=matter_type,
                    defaults={'default_reminder_days': DEFAULT_REMINDER_DAYS},
                )
                if was_created:
                    created += 1
                    self.stdout.write(f'  Created: {obj}')

        self.stdout.write(self.style.SUCCESS(f'\n{created} deadline types created.'))

        if options['with_samples']:
            self._create_samples()

    def _create_samples(self):
        today = timezone.localdate()
        self.stdout.write('\nCreating sample data...')

        # Sample clients
        client1, _ = Client.objects.get_or_create(
            name='Acme Development Corp',
            defaults={
                'email': 'jsmith@acmedev.com',
                'phone': '(303) 555-0101',
                'notes': 'Major commercial developer',
            }
        )
        client2, _ = Client.objects.get_or_create(
            name='Mountain View LLC',
            defaults={
                'email': 'sarah@mountainviewllc.com',
                'phone': '(303) 555-0202',
            }
        )
        client3, _ = Client.objects.get_or_create(
            name='Riverside Properties',
            defaults={
                'email': 'info@riversideprops.com',
                'phone': '(720) 555-0303',
            }
        )

        # Deadline types
        dd_exp = DeadlineType.objects.get(name='DD Expiration')
        closing = DeadlineType.objects.get(name='Closing Date')
        ext_elect = DeadlineType.objects.get(name='Extension Election Deadline')
        financing = DeadlineType.objects.get(name='Financing Contingency')
        inspection = DeadlineType.objects.get(name='Inspection Deadline')
        hearing = DeadlineType.objects.get(name='Hearing Date')
        filing = DeadlineType.objects.get(name='Application Filing Date')
        resubmit = DeadlineType.objects.get(name='Resubmittal Deadline')
        appeal = DeadlineType.objects.get(name='Appeal Deadline')

        # Transaction 1: Active deal with upcoming deadlines
        matter1, _ = Matter.objects.get_or_create(
            title='Office Building Acquisition - 123 Main St',
            client=client1,
            defaults={
                'matter_type': 'transaction',
                'property_address': '123 Main Street, Denver, CO 80202',
                'status': 'active',
            }
        )
        self._create_deadline(matter1, dd_exp, today + datetime.timedelta(days=5))
        self._create_deadline(matter1, ext_elect, today + datetime.timedelta(days=3))
        self._create_deadline(matter1, financing, today + datetime.timedelta(days=18))
        self._create_deadline(matter1, closing, today + datetime.timedelta(days=35))

        # Transaction 2: Deal with an overdue deadline
        matter2, _ = Matter.objects.get_or_create(
            title='Retail Center Purchase - Canyon Blvd',
            client=client2,
            defaults={
                'matter_type': 'transaction',
                'property_address': '456 Canyon Blvd, Boulder, CO 80302',
                'status': 'active',
            }
        )
        self._create_deadline(matter2, inspection, today - datetime.timedelta(days=2),
                              description='Phase I ESA results pending')
        self._create_deadline(matter2, dd_exp, today + datetime.timedelta(days=12))
        self._create_deadline(matter2, closing, today + datetime.timedelta(days=45))

        # Land Use: Rezoning application
        matter3, _ = Matter.objects.get_or_create(
            title='Rezoning Application - Riverside Parcel',
            client=client3,
            defaults={
                'matter_type': 'land_use',
                'property_address': '789 River Road, Lakewood, CO 80228',
                'status': 'active',
            }
        )
        self._create_deadline(matter3, filing, today - datetime.timedelta(days=10), status='completed')
        self._create_deadline(matter3, resubmit, today + datetime.timedelta(days=7),
                              description='Updated traffic study needed')
        self._create_deadline(matter3, hearing, today + datetime.timedelta(days=28))
        self._create_deadline(matter3, appeal, today + datetime.timedelta(days=58))

        # Land Use: PUD application
        matter4, _ = Matter.objects.get_or_create(
            title='PUD Amendment - Tech Campus Phase 2',
            client=client1,
            defaults={
                'matter_type': 'land_use',
                'property_address': '1000 Innovation Dr, Broomfield, CO 80021',
                'status': 'active',
            }
        )
        self._create_deadline(matter4, filing, today + datetime.timedelta(days=1))
        self._create_deadline(matter4, hearing, today + datetime.timedelta(days=42))

        self.stdout.write(self.style.SUCCESS('Sample data created successfully!'))

    def _create_deadline(self, matter, deadline_type, date, description='', status='upcoming'):
        Deadline.objects.get_or_create(
            matter=matter,
            deadline_type=deadline_type,
            defaults={
                'date': date,
                'description': description,
                'status': status,
            }
        )
