from django import template

register = template.Library()


@register.filter
def abs_value(value):
    """Return absolute value."""
    try:
        return abs(int(value))
    except (ValueError, TypeError):
        return value
