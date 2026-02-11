"""
Management command to send deadline reminder emails.

Usage:
    python manage.py send_reminders              # Send all due reminders
    python manage.py send_reminders --dry-run     # Preview without sending
    python manage.py send_reminders --verbose     # Show detailed output

Schedule via cron:
    0 8 * * * cd /path/to/deadline-tracker && venv/bin/python manage.py send_reminders
"""

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
from deadlines.models import Deadline, ReminderLog


class Command(BaseCommand):
    help = 'Send email reminders for upcoming deadlines'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview reminders without sending emails',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        today = timezone.localdate()

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no emails will be sent\n'))

        # Get all upcoming deadlines for active matters
        deadlines = Deadline.objects.filter(
            status='upcoming',
            matter__status='active',
        ).select_related('matter', 'matter__client', 'deadline_type')

        sent_count = 0
        skip_count = 0

        for deadline in deadlines:
            days_until = (deadline.date - today).days
            reminder_days = deadline.effective_reminder_days

            # Check if today matches any reminder interval
            if days_until not in reminder_days and days_until >= 0:
                continue

            # For overdue deadlines, send daily reminders
            if days_until < 0 and days_until < -7:
                # Stop nagging after 7 days overdue
                continue

            recipient = deadline.matter.client.email
            if not recipient:
                if verbose:
                    self.stdout.write(
                        self.style.WARNING(f'  SKIP: No email for {deadline.matter.client.name}')
                    )
                skip_count += 1
                continue

            # Check if this reminder was already sent
            already_sent = ReminderLog.objects.filter(
                deadline=deadline,
                days_before=days_until,
                status='sent',
                sent_at__date=today,
            ).exists()

            if already_sent:
                if verbose:
                    self.stdout.write(
                        f'  SKIP: Already sent {days_until}d reminder for {deadline}'
                    )
                skip_count += 1
                continue

            # Build the email
            subject = self._build_subject(deadline, days_until)
            html_body = render_to_string('deadlines/email/reminder.html', {
                'deadline': deadline,
                'client_name': deadline.matter.client.name,
                'days_until': days_until,
            })
            plain_body = self._build_plain_text(deadline, days_until)

            if verbose or dry_run:
                self.stdout.write(
                    f'  {"WOULD SEND" if dry_run else "SENDING"}: '
                    f'{subject} → {recipient}'
                )

            if not dry_run:
                try:
                    send_mail(
                        subject=subject,
                        message=plain_body,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[recipient],
                        html_message=html_body,
                        fail_silently=False,
                    )
                    ReminderLog.objects.create(
                        deadline=deadline,
                        recipient_email=recipient,
                        days_before=days_until,
                        status='sent',
                    )
                    sent_count += 1
                except Exception as e:
                    ReminderLog.objects.create(
                        deadline=deadline,
                        recipient_email=recipient,
                        days_before=days_until,
                        status='failed',
                        error_message=str(e),
                    )
                    self.stderr.write(
                        self.style.ERROR(f'  FAILED: {deadline} — {e}')
                    )
            else:
                sent_count += 1

        # Summary
        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN complete: {sent_count} reminders would be sent, {skip_count} skipped'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Done: {sent_count} reminders sent, {skip_count} skipped'
            ))

    def _build_subject(self, deadline, days_until):
        matter_title = deadline.matter.title
        dl_type = deadline.deadline_type.name

        if days_until < 0:
            return f'OVERDUE: {dl_type} — {matter_title}'
        elif days_until == 0:
            return f'TODAY: {dl_type} — {matter_title}'
        elif days_until == 1:
            return f'TOMORROW: {dl_type} — {matter_title}'
        else:
            return f'{days_until} Days: {dl_type} — {matter_title}'

    def _build_plain_text(self, deadline, days_until):
        lines = [
            f'Deadline Reminder',
            f'',
            f'Dear {deadline.matter.client.name},',
            f'',
        ]

        if days_until == 0:
            lines.append(f'This is a reminder that the following deadline is TODAY:')
        elif days_until == 1:
            lines.append(f'This is a reminder that the following deadline is TOMORROW:')
        elif days_until < 0:
            lines.append(f'The following deadline is OVERDUE by {abs(days_until)} day(s):')
        else:
            lines.append(f'The following deadline is in {days_until} days:')

        lines.extend([
            f'',
            f'  Deadline: {deadline.deadline_type.name}',
            f'  Date: {deadline.date.strftime("%A, %B %d, %Y")}',
            f'  Matter: {deadline.matter.title}',
        ])

        if deadline.matter.property_address:
            lines.append(f'  Property: {deadline.matter.property_address}')

        if deadline.description:
            lines.append(f'  Details: {deadline.description}')

        lines.extend([
            f'',
            f'If you have questions, please contact us.',
            f'',
            f'Best regards,',
            f'Your Legal Team',
        ])

        return '\n'.join(lines)
