def early_warning_alert_count(request):
    try:
        from early_warning.views import _build_early_warning_alerts

        alerts = _build_early_warning_alerts(request)
        return {
            'early_warning_alert_count': sum(1 for alert in alerts if alert.get('unread', True)),
        }
    except Exception:
        return {
            'early_warning_alert_count': 0,
        }