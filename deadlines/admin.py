from django.contrib import admin
from .models import Client, Matter, DeadlineType, Deadline, ReminderLog


class MatterInline(admin.TabularInline):
    model = Matter
    extra = 0
    fields = ['title', 'matter_type', 'property_address', 'status']
    show_change_link = True


class DeadlineInline(admin.TabularInline):
    model = Deadline
    extra = 1
    fields = ['deadline_type', 'date', 'status', 'description']
    autocomplete_fields = ['deadline_type']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'active_matters_count', 'created_at']
    search_fields = ['name', 'email']
    inlines = [MatterInline]

    def active_matters_count(self, obj):
        return obj.active_matters_count
    active_matters_count.short_description = 'Active Matters'


@admin.register(Matter)
class MatterAdmin(admin.ModelAdmin):
    list_display = ['title', 'client', 'matter_type', 'property_address', 'status', 'next_deadline_display', 'created_at']
    list_filter = ['matter_type', 'status']
    search_fields = ['title', 'client__name', 'property_address']
    autocomplete_fields = ['client']
    inlines = [DeadlineInline]

    def next_deadline_display(self, obj):
        dl = obj.next_deadline
        if dl:
            return f"{dl.deadline_type.name}: {dl.date}"
        return "—"
    next_deadline_display.short_description = 'Next Deadline'


@admin.register(DeadlineType)
class DeadlineTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'matter_type', 'default_reminder_days']
    list_filter = ['matter_type']
    search_fields = ['name']


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ['deadline_type', 'matter', 'date', 'days_until_display', 'status']
    list_filter = ['status', 'deadline_type__matter_type', 'deadline_type']
    search_fields = ['matter__title', 'matter__client__name', 'deadline_type__name']
    autocomplete_fields = ['matter', 'deadline_type']
    date_hierarchy = 'date'

    def days_until_display(self, obj):
        days = obj.days_until
        if days < 0:
            return f"{abs(days)}d OVERDUE"
        elif days == 0:
            return "TODAY"
        else:
            return f"{days}d"
    days_until_display.short_description = 'Days Until'


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ['deadline', 'recipient_email', 'days_before', 'status', 'sent_at']
    list_filter = ['status']
    readonly_fields = ['deadline', 'sent_at', 'recipient_email', 'days_before', 'status', 'error_message']


# Customize admin site header
admin.site.site_header = "Deadline Tracker"
admin.site.site_title = "Deadline Tracker Admin"
admin.site.index_title = "Manage Deadlines"
