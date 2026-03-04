from django import forms
from .models import Client, Matter, Deadline


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class MatterForm(forms.ModelForm):
    client_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Type client name',
        }),
        help_text='Type a client name. If they don\'t exist yet, a new client record will be created.',
    )

    class Meta:
        model = Matter
        fields = ['title', 'matter_type', 'property_address', 'status', 'asana_project_id', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'matter_type': forms.Select(attrs={'class': 'form-select'}),
            'property_address': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'asana_project_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional — Asana project GID'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill client name when editing an existing matter
        if self.instance and self.instance.pk:
            self.fields['client_name'].initial = self.instance.client.name

    def save(self, commit=True):
        client_name = self.cleaned_data['client_name'].strip()
        client, _ = Client.objects.get_or_create(
            name__iexact=client_name,
            defaults={'name': client_name},
        )
        self.instance.client = client
        return super().save(commit=commit)


class DeadlineForm(forms.ModelForm):
    class Meta:
        model = Deadline
        fields = ['deadline_type', 'date', 'description', 'reminder_days', 'status']
        widgets = {
            'deadline_type': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'reminder_days': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 30, 14, 7, 3, 1 (leave blank for defaults)'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, matter_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        if matter_type:
            self.fields['deadline_type'].queryset = self.fields['deadline_type'].queryset.filter(
                matter_type=matter_type
            )

    def clean_reminder_days(self):
        value = self.cleaned_data.get('reminder_days')
        if not value:
            return []
        if isinstance(value, list):
            return value
        # Parse comma-separated string
        try:
            days = [int(d.strip()) for d in str(value).split(',') if d.strip()]
            return sorted(days, reverse=True)
        except ValueError:
            raise forms.ValidationError('Enter comma-separated numbers, e.g. 30, 14, 7, 3, 1')
