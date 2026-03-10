import datetime


def add_business_days(start_date, num_days):
    """
    Add business days (Monday-Friday) to a date.

    Does not account for federal holidays — for MVP, weekday-only
    calculation is sufficient. Holiday handling can be added later.
    """
    current = start_date
    added = 0
    while added < num_days:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:  # Monday=0 through Friday=4
            added += 1
    return current
