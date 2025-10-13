from django import template
import datetime

register = template.Library()

@register.filter
def format_time_duration(seconds):
    if seconds is None:
        return "N/A"
    try:
        seconds = float(seconds)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "00:00:00"