import datetime

from django.db import models
from django.utils import timezone

from .utils import add_business_days


class Client(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def active_matters_count(self):
        return self.matters.filter(status='active').count()


class Matter(models.Model):
    MATTER_TYPE_CHOICES = [
        ('transaction', 'Real Estate Transaction'),
        ('land_use', 'Land Use / Zoning'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('closed', 'Closed'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='matters')
    title = models.CharField(max_length=300)
    matter_type = models.CharField(max_length=20, choices=MATTER_TYPE_CHOICES)
    property_address = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    asana_project_id = models.CharField(max_length=100, blank=True, help_text='Asana project GID for syncing')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.client.name})"

    @property
    def upcoming_deadlines(self):
        return self.deadlines.filter(
            status='upcoming',
            date__gte=timezone.localdate()
        ).order_by('date')

    @property
    def overdue_deadlines(self):
        return self.deadlines.filter(
            status='upcoming',
            date__lt=timezone.localdate()
        ).order_by('date')

    @property
    def next_deadline(self):
        return self.upcoming_deadlines.first()


class MatterContact(models.Model):
    """An email recipient for notifications on a specific matter."""
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=200)
    email = models.EmailField()
    role = models.CharField(max_length=100, blank=True, help_text='e.g. Client, Buyer, Seller, Broker, Lender')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} <{self.email}> ({self.role})"


class DeadlineType(models.Model):
    MATTER_TYPE_CHOICES = Matter.MATTER_TYPE_CHOICES
    DAY_TYPE_CHOICES = [
        ('calendar', 'Calendar Days'),
        ('business', 'Business Days'),
    ]

    name = models.CharField(max_length=200)
    matter_type = models.CharField(max_length=20, choices=MATTER_TYPE_CHOICES)
    default_reminder_days = models.JSONField(
        default=list,
        help_text='List of days before deadline to send reminders, e.g. [30, 14, 7, 3, 1]'
    )
    default_reference_type = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dependent_types',
        help_text='Default reference deadline type for calculated dates',
    )
    default_offset_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Default number of days offset from reference deadline',
    )
    default_day_type = models.CharField(
        max_length=10,
        choices=DAY_TYPE_CHOICES,
        default='calendar',
        help_text='Default day type for offset calculation',
    )

    class Meta:
        ordering = ['matter_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_matter_type_display()})"


class Deadline(models.Model):
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('completed', 'Completed'),
        ('extended', 'Extended'),
        ('waived', 'Waived'),
    ]
    DAY_TYPE_CHOICES = [
        ('calendar', 'Calendar Days'),
        ('business', 'Business Days'),
    ]

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name='deadlines')
    deadline_type = models.ForeignKey(DeadlineType, on_delete=models.PROTECT, related_name='deadlines')
    date = models.DateField()
    description = models.TextField(blank=True, help_text='Additional details about this specific deadline')
    reminder_days = models.JSONField(
        default=list,
        blank=True,
        help_text='Override reminder days for this deadline. Leave empty to use deadline type defaults.'
    )
    notify = models.BooleanField(default=False, help_text='Send email reminders to matter contacts for this deadline')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='upcoming')
    asana_task_id = models.CharField(max_length=100, blank=True, help_text='Asana task GID if synced')

    # Calculated date fields
    is_calculated = models.BooleanField(
        default=False,
        help_text='Whether this date is calculated from a reference deadline',
    )
    reference_deadline = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dependents',
        help_text='The deadline this date is calculated from',
    )
    offset_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Number of days offset from reference deadline',
    )
    day_type = models.CharField(
        max_length=10,
        choices=DAY_TYPE_CHOICES,
        default='calendar',
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.deadline_type.name} - {self.date} ({self.matter.title})"

    @property
    def effective_reminder_days(self):
        """Use deadline-specific reminder days if set, otherwise fall back to type defaults."""
        if self.reminder_days:
            return self.reminder_days
        return self.deadline_type.default_reminder_days

    @property
    def days_until(self):
        """Days until this deadline. Negative means overdue."""
        return (self.date - timezone.localdate()).days

    @property
    def urgency(self):
        """Return urgency level for color coding."""
        days = self.days_until
        if days < 0:
            return 'overdue'
        elif days <= 3:
            return 'critical'
        elif days <= 7:
            return 'warning'
        elif days <= 14:
            return 'attention'
        else:
            return 'normal'

    @property
    def urgency_color(self):
        colors = {
            'overdue': 'danger',
            'critical': 'danger',
            'warning': 'warning',
            'attention': 'info',
            'normal': 'success',
        }
        return colors.get(self.urgency, 'secondary')

    def recalculate_date(self):
        """Recalculate this deadline's date from its reference deadline."""
        if not self.is_calculated or not self.reference_deadline or self.offset_days is None:
            return False
        base_date = self.reference_deadline.date
        if self.day_type == 'business':
            self.date = add_business_days(base_date, self.offset_days)
        else:
            self.date = base_date + datetime.timedelta(days=self.offset_days)
        return True

    def recalculate_dependents(self, visited=None):
        """Recalculate all deadlines that depend on this one (cascading)."""
        if visited is None:
            visited = set()
        if self.pk in visited:
            return  # Prevent circular references
        visited.add(self.pk)
        for dep in self.dependents.filter(is_calculated=True):
            if dep.recalculate_date():
                dep.save()
                dep.recalculate_dependents(visited=visited)


class ReminderLog(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    deadline = models.ForeignKey(Deadline, on_delete=models.CASCADE, related_name='reminder_logs')
    sent_at = models.DateTimeField(auto_now_add=True)
    recipient_email = models.EmailField()
    days_before = models.IntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Reminder to {self.recipient_email} - {self.days_before}d before {self.deadline}"
