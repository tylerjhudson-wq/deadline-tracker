"""
Management command to sync deadlines from Asana projects.

Usage:
    python manage.py sync_asana                # Sync all linked matters
    python manage.py sync_asana --dry-run      # Preview without saving
    python manage.py sync_asana --verbose       # Show detailed output

Schedule via cron:
    */30 * * * * cd /path/to/deadline-tracker && venv/bin/python manage.py sync_asana
"""

import asana
from asana.rest import ApiException
from django.core.management.base import BaseCommand
from django.conf import settings
from deadlines.models import Matter, DeadlineType, Deadline


class Command(BaseCommand):
    help = 'Sync deadlines from Asana projects linked to matters'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview sync without saving changes',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
        parser.add_argument(
            '--matter-id',
            type=int,
            help='Sync only a specific matter by ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']

        if not settings.ASANA_ACCESS_TOKEN:
            self.stderr.write(self.style.ERROR(
                'ASANA_ACCESS_TOKEN is not set. Add it to your .env file.'
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be saved\n'))

        # Initialize Asana client (v5 SDK)
        configuration = asana.Configuration()
        configuration.access_token = settings.ASANA_ACCESS_TOKEN
        api_client = asana.ApiClient(configuration)
        tasks_api = asana.TasksApi(api_client)

        # Get matters with Asana project IDs
        matters = Matter.objects.filter(
            asana_project_id__isnull=False,
            status='active',
        ).exclude(asana_project_id='')

        if options['matter_id']:
            matters = matters.filter(pk=options['matter_id'])

        if not matters.exists():
            self.stdout.write('No matters with Asana project IDs found.')
            return

        # Build a mapping of deadline type names (lowercased) to DeadlineType objects
        deadline_types = {dt.name.lower(): dt for dt in DeadlineType.objects.all()}

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for matter in matters:
            self.stdout.write(f'\nSyncing: {matter.title} (Asana project: {matter.asana_project_id})')

            try:
                opts = {
                    'opt_fields': 'name,due_on,completed,gid,notes',
                }
                tasks = tasks_api.get_tasks_for_project(
                    matter.asana_project_id,
                    opts,
                )

                for task in tasks:
                    task_name = getattr(task, 'name', '').strip()
                    due_on = getattr(task, 'due_on', None)
                    task_gid = getattr(task, 'gid', '')
                    is_completed = getattr(task, 'completed', False)

                    if not due_on:
                        if verbose:
                            self.stdout.write(f'  SKIP: "{task_name}" — no due date')
                        skipped_count += 1
                        continue

                    # Try to match task name to a DeadlineType
                    matched_type = self._match_deadline_type(task_name, deadline_types)

                    if not matched_type:
                        if verbose:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'  SKIP: "{task_name}" — no matching deadline type'
                                )
                            )
                        skipped_count += 1
                        continue

                    # Check if deadline already exists for this Asana task
                    existing = Deadline.objects.filter(
                        asana_task_id=task_gid,
                        matter=matter,
                    ).first()

                    if existing:
                        # Update if date changed
                        if str(existing.date) != str(due_on):
                            if verbose:
                                self.stdout.write(
                                    f'  UPDATE: "{task_name}" date {existing.date} → {due_on}'
                                )
                            if not dry_run:
                                existing.date = due_on
                                existing.save()
                            updated_count += 1
                        # Update status if completed in Asana
                        if is_completed and existing.status == 'upcoming':
                            if verbose:
                                self.stdout.write(f'  COMPLETE: "{task_name}"')
                            if not dry_run:
                                existing.status = 'completed'
                                existing.save()
                            updated_count += 1
                    else:
                        # Create new deadline
                        notes = getattr(task, 'notes', '') or ''
                        if verbose or dry_run:
                            self.stdout.write(
                                f'  {"WOULD CREATE" if dry_run else "CREATE"}: '
                                f'"{task_name}" → {matched_type.name} on {due_on}'
                            )
                        if not dry_run:
                            Deadline.objects.create(
                                matter=matter,
                                deadline_type=matched_type,
                                date=due_on,
                                description=notes[:500],
                                asana_task_id=task_gid,
                                status='completed' if is_completed else 'upcoming',
                            )
                        created_count += 1

            except ApiException as e:
                self.stderr.write(
                    self.style.ERROR(f'  Asana API error for {matter.title}: {e}')
                )
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'  ERROR syncing {matter.title}: {e}')
                )

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Sync complete: {created_count} created, {updated_count} updated, {skipped_count} skipped'
        ))

    def _match_deadline_type(self, task_name, deadline_types):
        """
        Try to match an Asana task name to a DeadlineType.

        Matching strategy:
        1. Exact match (case-insensitive)
        2. Task name contains deadline type name
        3. Deadline type name contains task name
        """
        name_lower = task_name.lower()

        # Exact match
        if name_lower in deadline_types:
            return deadline_types[name_lower]

        # Task name contains type name (e.g., "DD Expiration - Phase 1" matches "DD Expiration")
        for type_name, dt in deadline_types.items():
            if type_name in name_lower:
                return dt

        # Type name contains task name (e.g., task "Closing" matches "Closing Date")
        for type_name, dt in deadline_types.items():
            if name_lower in type_name:
                return dt

        return None
