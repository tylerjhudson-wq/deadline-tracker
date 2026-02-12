import os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Case, When, IntegerField
from .models import Client, Matter, Deadline, DeadlineType
from .forms import ClientForm, MatterForm, DeadlineForm


def dashboard(request):
    """Main dashboard showing all upcoming deadlines grouped by urgency."""
    today = timezone.localdate()

    # Filter parameters
    matter_type = request.GET.get('type', '')
    client_id = request.GET.get('client', '')
    status_filter = request.GET.get('status', 'active')

    # Base queryset: upcoming deadlines for active matters
    deadlines = Deadline.objects.filter(
        status='upcoming',
        matter__status__in=['active', 'on_hold'] if status_filter == 'all' else [status_filter or 'active'],
    ).select_related('matter', 'matter__client', 'deadline_type')

    if matter_type:
        deadlines = deadlines.filter(matter__matter_type=matter_type)
    if client_id:
        deadlines = deadlines.filter(matter__client_id=client_id)

    # Group by urgency
    import datetime
    overdue = deadlines.filter(date__lt=today).order_by('date')
    this_week = deadlines.filter(
        date__gte=today,
        date__lte=today + datetime.timedelta(days=7)
    ).order_by('date')
    next_two_weeks = deadlines.filter(
        date__gt=today + datetime.timedelta(days=7),
        date__lte=today + datetime.timedelta(days=21)
    ).order_by('date')
    later = deadlines.filter(
        date__gt=today + datetime.timedelta(days=21)
    ).order_by('date')

    # Stats
    total_active_matters = Matter.objects.filter(status='active').count()
    total_upcoming = deadlines.count()

    clients = Client.objects.all()

    context = {
        'overdue': overdue,
        'this_week': this_week,
        'next_two_weeks': next_two_weeks,
        'later': later,
        'total_active_matters': total_active_matters,
        'total_upcoming': total_upcoming,
        'clients': clients,
        'filter_type': matter_type,
        'filter_client': client_id,
        'filter_status': status_filter,
        'today': today,
    }
    return render(request, 'deadlines/dashboard.html', context)


def matter_detail(request, pk):
    """Detail view for a single matter with all its deadlines."""
    matter = get_object_or_404(Matter.objects.select_related('client'), pk=pk)
    deadlines = matter.deadlines.select_related('deadline_type').all()
    reminder_logs = matter.deadlines.prefetch_related('reminder_logs').all()

    context = {
        'matter': matter,
        'deadlines': deadlines,
        'today': timezone.localdate(),
    }
    return render(request, 'deadlines/matter_detail.html', context)


def matter_create(request):
    """Create a new matter."""
    if request.method == 'POST':
        form = MatterForm(request.POST)
        if form.is_valid():
            matter = form.save()
            messages.success(request, f'Matter "{matter.title}" created successfully.')
            return redirect('deadlines:matter_detail', pk=matter.pk)
    else:
        form = MatterForm()

    return render(request, 'deadlines/matter_form.html', {
        'form': form,
        'title': 'New Matter',
    })


def matter_edit(request, pk):
    """Edit an existing matter."""
    matter = get_object_or_404(Matter, pk=pk)
    if request.method == 'POST':
        form = MatterForm(request.POST, instance=matter)
        if form.is_valid():
            form.save()
            messages.success(request, f'Matter "{matter.title}" updated.')
            return redirect('deadlines:matter_detail', pk=matter.pk)
    else:
        form = MatterForm(instance=matter)

    return render(request, 'deadlines/matter_form.html', {
        'form': form,
        'title': f'Edit: {matter.title}',
        'matter': matter,
    })


def deadline_add(request, matter_pk):
    """Add a deadline to a matter."""
    matter = get_object_or_404(Matter, pk=matter_pk)
    if request.method == 'POST':
        form = DeadlineForm(request.POST, matter_type=matter.matter_type)
        if form.is_valid():
            deadline = form.save(commit=False)
            deadline.matter = matter
            deadline.save()
            messages.success(request, f'Deadline "{deadline.deadline_type.name}" added.')
            return redirect('deadlines:matter_detail', pk=matter.pk)
    else:
        form = DeadlineForm(matter_type=matter.matter_type)

    return render(request, 'deadlines/deadline_form.html', {
        'form': form,
        'matter': matter,
        'title': f'Add Deadline to {matter.title}',
    })


def deadline_edit(request, pk):
    """Edit a deadline."""
    deadline = get_object_or_404(Deadline.objects.select_related('matter'), pk=pk)
    if request.method == 'POST':
        form = DeadlineForm(request.POST, instance=deadline, matter_type=deadline.matter.matter_type)
        if form.is_valid():
            form.save()
            messages.success(request, f'Deadline updated.')
            return redirect('deadlines:matter_detail', pk=deadline.matter.pk)
    else:
        form = DeadlineForm(instance=deadline, matter_type=deadline.matter.matter_type)

    return render(request, 'deadlines/deadline_form.html', {
        'form': form,
        'matter': deadline.matter,
        'title': f'Edit Deadline: {deadline.deadline_type.name}',
        'deadline': deadline,
    })


def deadline_complete(request, pk):
    """Mark a deadline as completed."""
    deadline = get_object_or_404(Deadline, pk=pk)
    if request.method == 'POST':
        deadline.status = 'completed'
        deadline.save()
        messages.success(request, f'"{deadline.deadline_type.name}" marked as completed.')
    return redirect('deadlines:matter_detail', pk=deadline.matter.pk)


def setup_admin(request):
    """One-time setup: create admin user and seed data. Visit /setup/ to run."""
    from .management.commands.seed_data import DEADLINE_TYPES, DEFAULT_REMINDER_DAYS

    output = []

    # Seed deadline types
    for matter_type, type_names in DEADLINE_TYPES.items():
        for name in type_names:
            obj, created = DeadlineType.objects.get_or_create(
                name=name,
                matter_type=matter_type,
                defaults={'default_reminder_days': DEFAULT_REMINDER_DAYS},
            )
            if created:
                output.append(f'Created deadline type: {name}')

    # Create/reset admin user
    username = os.getenv('DJANGO_ADMIN_USERNAME', 'admin')
    password = os.getenv('DJANGO_ADMIN_PASSWORD', 'changeme123')
    User.objects.filter(username=username).delete()
    user = User.objects.create_superuser(username=username, email='admin@firm.com', password=password)
    output.append(f'\nAdmin user created: username="{username}", has_password={user.has_usable_password()}')
    output.append(f'Total users in database: {User.objects.count()}')
    output.append(f'\nNow go to /admin/ and log in with username "{username}" and the password you set in DJANGO_ADMIN_PASSWORD')
    output.append(f'(If you did not set DJANGO_ADMIN_PASSWORD, the default password is: changeme123)')

    return HttpResponse('\n'.join(output), content_type='text/plain')


def client_create(request):
    """Create a new client."""
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f'Client "{client.name}" created.')
            # If came from matter form, redirect back
            next_url = request.GET.get('next', 'deadlines:dashboard')
            return redirect(next_url)
    else:
        form = ClientForm()

    return render(request, 'deadlines/client_form.html', {
        'form': form,
        'title': 'New Client',
    })
