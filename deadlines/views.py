import datetime
import os

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Case, When, IntegerField
from .models import Client, Matter, MatterContact, Deadline, DeadlineType
from .forms import ClientForm, MatterForm, DeadlineForm
from .utils import add_business_days


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
    deadlines = matter.deadlines.select_related(
        'deadline_type', 'reference_deadline__deadline_type'
    ).all()
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
            messages.success(request, f'Matter "{matter.title}" created. Now select deadlines.')
            return redirect('deadlines:matter_deadlines_setup', pk=matter.pk)
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


def matter_deadlines_setup(request, pk):
    """Checklist page to select and date multiple deadlines at once."""
    matter = get_object_or_404(Matter, pk=pk)
    deadline_types = DeadlineType.objects.filter(
        matter_type=matter.matter_type
    ).select_related('default_reference_type')

    # Get already-existing deadline type IDs for this matter
    existing_type_ids = set(matter.deadlines.values_list('deadline_type_id', flat=True))
    existing_deadlines = matter.deadlines.select_related('deadline_type').all()

    if request.method == 'POST':
        created_deadlines = {}  # dt_id -> Deadline instance
        created_count = 0

        # PASS 1: Create all hard-dated deadlines first
        for dt in deadline_types:
            checkbox_key = f'check_{dt.id}'
            if checkbox_key not in request.POST or dt.id in existing_type_ids:
                continue

            mode = request.POST.get(f'mode_{dt.id}', 'hard')
            if mode == 'hard':
                date_value = request.POST.get(f'date_{dt.id}')
                if date_value:
                    dl = Deadline.objects.create(
                        matter=matter,
                        deadline_type=dt,
                        date=date_value,
                        is_calculated=False,
                    )
                    created_deadlines[dt.id] = dl
                    created_count += 1

        # PASS 2: Create calculated deadlines (they need reference deadlines to exist)
        for dt in deadline_types:
            checkbox_key = f'check_{dt.id}'
            if checkbox_key not in request.POST or dt.id in existing_type_ids:
                continue

            mode = request.POST.get(f'mode_{dt.id}', 'hard')
            if mode == 'calculated':
                ref_type_id = request.POST.get(f'ref_{dt.id}')
                offset = request.POST.get(f'offset_{dt.id}')
                day_type = request.POST.get(f'daytype_{dt.id}', 'calendar')

                if ref_type_id and offset:
                    try:
                        ref_type_id = int(ref_type_id)
                        offset_int = int(offset)
                    except (ValueError, TypeError):
                        continue

                    # Find the reference deadline — could be one we just created,
                    # or one that already existed for this matter
                    ref_deadline = created_deadlines.get(ref_type_id)
                    if not ref_deadline:
                        ref_deadline = Deadline.objects.filter(
                            matter=matter,
                            deadline_type_id=ref_type_id,
                        ).first()

                    if ref_deadline:
                        if day_type == 'business':
                            calc_date = add_business_days(ref_deadline.date, offset_int)
                        else:
                            calc_date = ref_deadline.date + datetime.timedelta(days=offset_int)

                        dl = Deadline.objects.create(
                            matter=matter,
                            deadline_type=dt,
                            date=calc_date,
                            is_calculated=True,
                            reference_deadline=ref_deadline,
                            offset_days=offset_int,
                            day_type=day_type,
                        )
                        created_deadlines[dt.id] = dl
                        created_count += 1

        if created_count:
            messages.success(request, f'{created_count} deadline(s) added. Now set up notifications.')
            return redirect('deadlines:matter_notifications_setup', pk=matter.pk)
        else:
            messages.info(request, 'No new deadlines added.')
            return redirect('deadlines:matter_detail', pk=matter.pk)

    context = {
        'matter': matter,
        'deadline_types': deadline_types,
        'existing_type_ids': existing_type_ids,
        'existing_deadlines': existing_deadlines,
    }
    return render(request, 'deadlines/matter_deadlines_setup.html', context)


def matter_notifications_setup(request, pk):
    """Set up contacts and choose which deadlines trigger notifications."""
    matter = get_object_or_404(Matter, pk=pk)
    deadlines = matter.deadlines.select_related('deadline_type').filter(status='upcoming').order_by('date')
    contacts = matter.contacts.all()

    if request.method == 'POST':
        # Handle adding a new contact
        if 'add_contact' in request.POST:
            contact_name = request.POST.get('contact_name', '').strip()
            contact_email = request.POST.get('contact_email', '').strip()
            contact_role = request.POST.get('contact_role', '').strip()
            if contact_name and contact_email:
                MatterContact.objects.create(
                    matter=matter,
                    name=contact_name,
                    email=contact_email,
                    role=contact_role,
                )
                messages.success(request, f'Contact "{contact_name}" added.')
            return redirect('deadlines:matter_notifications_setup', pk=matter.pk)

        # Handle removing a contact
        if 'remove_contact' in request.POST:
            contact_id = request.POST.get('remove_contact')
            MatterContact.objects.filter(id=contact_id, matter=matter).delete()
            messages.success(request, 'Contact removed.')
            return redirect('deadlines:matter_notifications_setup', pk=matter.pk)

        # Handle saving notification preferences (which deadlines get notifications)
        if 'save_notifications' in request.POST:
            for deadline in deadlines:
                notify_key = f'notify_{deadline.id}'
                deadline.notify = notify_key in request.POST
                deadline.save()
            messages.success(request, 'Notification preferences saved.')
            return redirect('deadlines:matter_detail', pk=matter.pk)

    context = {
        'matter': matter,
        'deadlines': deadlines,
        'contacts': contacts,
    }
    return render(request, 'deadlines/matter_notifications_setup.html', context)


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
            deadline = form.save()
            # Recalculate any deadlines that depend on this one
            deadline.recalculate_dependents()
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
    """Setup page disabled after initial use."""
    return HttpResponse('Setup already completed. Use /admin/ to manage the app.', content_type='text/plain')


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
