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


def user_role_context(request):
    """Expose role-based flags to every template."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {
            'user_role': None,
            'can_monitor': False,
            'can_manage_data': False,
            'can_manage_users': False,
            'is_community_member': False,
        }
    try:
        role = request.user.profile.role
    except Exception:
        role = None

    monitoring_roles = {'system_admin', 'doe_officer', 'dma_officer', 'nul_researcher'}
    data_roles       = {'system_admin', 'doe_officer', 'dma_officer'}

    return {
        'user_role':           role,
        'can_monitor':         role in monitoring_roles,
        'can_manage_data':     role in data_roles,
        'can_manage_users':    role == 'system_admin',
        'is_community_member': role == 'community_member',
    }
