import json
from datetime import date, timedelta

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone

from mapping.models import CommunityInput, Wetland, WetlandMonitoringRecord


SESSION_READ_ALERTS_KEY = 'read_early_warning_alerts'


def _alert_key(alert):
    return '|'.join([
        str(alert.get('wetland_id') or ''),
        str(alert.get('trigger_year') or ''),
        str(alert.get('category') or ''),
        str(alert.get('source') or ''),
    ])


def _get_read_alert_keys(request):
    session = getattr(request, 'session', None)
    if session is None:
        return set()
    return set(session.get(SESSION_READ_ALERTS_KEY, []))


def _save_read_alert_key(request, alert_key):
    session = getattr(request, 'session', None)
    if session is None or not alert_key:
        return False

    read_alerts = set(session.get(SESSION_READ_ALERTS_KEY, []))
    if alert_key in read_alerts:
        return False

    read_alerts.add(alert_key)
    session[SESSION_READ_ALERTS_KEY] = sorted(read_alerts)
    session.modified = True
    return True


def _apply_read_state(request, alerts):
    read_alerts = _get_read_alert_keys(request)
    for alert in alerts:
        alert['alert_key'] = _alert_key(alert)
        alert['unread'] = alert['alert_key'] not in read_alerts
    return alerts


def _safe_pct_change(previous, current):
    if previous is None or current is None:
        return None
    denominator = abs(previous) if abs(previous) > 1e-6 else None
    if denominator is None:
        return None
    return ((current - previous) / denominator) * 100.0


def _relative_time_from_year(year_value):
    if not year_value:
        return 'Unknown time'
    current_year = timezone.now().year
    delta = current_year - int(year_value)
    if delta <= 0:
        return 'This year'
    if delta == 1:
        return '1 year ago'
    return f'{delta} years ago'


def _wetland_location_label(wetland):
    return getattr(wetland, 'district', None) or wetland.village or 'Unknown'


def _year_span_text(previous_year, current_year):
    if previous_year and current_year:
        return f'from {int(previous_year)} to {int(current_year)}'
    if current_year:
        return f'in {int(current_year)}'
    return 'across the available records'


_COMMUNITY_SEVERITY_SCORE = {'critical': 1.0, 'warning': 0.7, 'info': 0.3}

_OBSERVATION_LABELS = {
    'grazing': 'Grazing pressure',
    'erosion': 'Active erosion',
    'invasive_species': 'Invasive species',
}


def _relative_time_label(dt):
    now = timezone.now()
    delta = now - dt
    if delta.days == 0:
        hours = delta.seconds // 3600
        return f'{hours}h ago' if hours > 0 else 'Just now'
    if delta.days == 1:
        return 'Yesterday'
    if delta.days < 7:
        return f'{delta.days} days ago'
    if delta.days < 30:
        weeks = delta.days // 7
        return f'{weeks} week{"s" if weeks > 1 else ""} ago'
    if delta.days < 365:
        months = delta.days // 30
        return f'{months} month{"s" if months > 1 else ""} ago'
    years = delta.days // 365
    return f'{years} year{"s" if years > 1 else ""} ago'


def _community_input_alerts():
    """Convert recent community field reports into early-warning alert dicts."""
    cutoff = timezone.now() - timedelta(days=90)
    entries = (
        CommunityInput.objects
        .select_related('wetland')
        .filter(created_at__gte=cutoff)
        .exclude(severity='resolved')
        .order_by('-created_at')
    )
    alerts = []
    for entry in entries:
        obs_label = _OBSERVATION_LABELS.get(entry.observation, entry.get_observation_display())
        submitter = entry.submitted_by or 'Anonymous'
        alerts.append({
            'severity': entry.severity,
            'title': f'Field report: {obs_label} at {entry.wetland.name}',
            'desc': (
                f'{entry.comments} '
                f'— Reported by {submitter} ({_relative_time_label(entry.created_at)}).'
            ),
            'wetland_id': entry.wetland_id,
            'trigger_year': entry.id,
            'site': entry.wetland.name,
            'district': entry.wetland.village or 'Unknown',
            'category': f'Community: {obs_label}',
            'source': 'community_input',
            'time': _relative_time_label(entry.created_at),
            'date': entry.created_at.date().isoformat(),
            'unread': True,
            'score': _COMMUNITY_SEVERITY_SCORE.get(entry.severity, 0.3),
            'thresholds': {
                'observation': entry.observation,
                'submitted_by': submitter,
                'input_id': entry.id,
            },
        })
    return alerts


def _compose_composite_alert(wetland, current_record, metrics):
    ndvi_decline_pct = metrics.get('ndvi_decline_pct')
    bsi_current = metrics.get('bsi_current')
    bsi_increase_pct = metrics.get('bsi_increase_pct')
    lst_current = metrics.get('lst_current')
    lst_increase = metrics.get('lst_increase')
    erosion_risk = metrics.get('erosion_risk')
    ndvi_year_span = metrics.get('ndvi_year_span') or 'across the available records'
    bsi_year_span = metrics.get('bsi_year_span') or 'across the available records'
    lst_year_span = metrics.get('lst_year_span') or 'across the available records'

    score = 0.0
    reasons = []
    warning_rules = 0
    critical_rules = 0

    if ndvi_decline_pct is not None:
        if ndvi_decline_pct >= 35:
            score += 0.35
            reasons.append(f'NDVI declined by {ndvi_decline_pct:.1f}% {ndvi_year_span}')
            critical_rules += 1
        elif ndvi_decline_pct >= 20:
            score += 0.25
            reasons.append(f'NDVI declined by {ndvi_decline_pct:.1f}% {ndvi_year_span}')
            warning_rules += 1

    if bsi_current is not None:
        if bsi_current >= 0.25:
            score += 0.30
            reasons.append(f'BSI is high at {bsi_current:.3f}')
            critical_rules += 1
        elif bsi_current >= 0.18:
            score += 0.20
            reasons.append(f'BSI elevated at {bsi_current:.3f}')
            warning_rules += 1

    if bsi_increase_pct is not None:
        if bsi_increase_pct >= 20:
            score += 0.20
            reasons.append(f'BSI increased by {bsi_increase_pct:.1f}% {bsi_year_span}')
            warning_rules += 1
        elif bsi_increase_pct >= 10:
            score += 0.10
            reasons.append(f'BSI increased by {bsi_increase_pct:.1f}% {bsi_year_span}')

    if lst_current is not None:
        if lst_current >= 30:
            score += 0.25
            reasons.append(f'LST reached {lst_current:.1f}°C')
            critical_rules += 1
        elif lst_current >= 26:
            score += 0.15
            reasons.append(f'LST elevated at {lst_current:.1f}°C')
            warning_rules += 1

    if lst_increase is not None and lst_increase >= 2:
        score += 0.10
        reasons.append(f'LST increased by {lst_increase:.1f}°C {lst_year_span}')
        warning_rules += 1

    if erosion_risk is not None:
        if erosion_risk >= 1.5:
            score += 0.20
            reasons.append(f'Erosion risk is {erosion_risk:.2f}')
            warning_rules += 1
        elif erosion_risk >= 1.0:
            score += 0.10
            reasons.append(f'Erosion risk is {erosion_risk:.2f}')

    score = min(score, 1.0)
    if critical_rules >= 1 or warning_rules >= 2:
        severity = 'critical'
    elif warning_rules == 1:
        severity = 'warning'
    else:
        severity = 'info'

    if warning_rules == 0 and critical_rules == 0 and score < 0.30:
        return None

    reason_text = '; '.join(reasons) if reasons else 'Pattern shift detected in ecological indicators'
    return {
        'severity': severity,
        'title': f'Composite early warning triggered for {wetland.name}',
        'desc': (
            f'Composite risk score is {score:.2f}. '
            f'Rule triggers: warning={warning_rules}, severe={critical_rules}. Drivers: {reason_text}.'
        ),
        'wetland_id': wetland.id,
        'trigger_year': current_record.year,
        'site': wetland.name,
        'district': _wetland_location_label(wetland),
        'category': 'Rule Composite Risk',
        'source': 'Rule-based threshold engine (composite)',
        'time': _relative_time_from_year(current_record.year),
        'date': date(current_record.year, 1, 1).isoformat(),
        'unread': True,
        'score': round(score, 3),
        'thresholds': {
            'ndvi_decline_pct': ndvi_decline_pct,
            'bsi_increase_pct': bsi_increase_pct,
            'lst_increase_c': lst_increase,
            'warning_rule_count': warning_rules,
            'severe_rule_count': critical_rules,
        },
    }


def _build_early_warning_alerts(request=None):
    # Community field reports come first — they represent ground-truth observations
    alerts = _community_input_alerts()

    wetlands = Wetland.objects.filter(is_current=True)
    for wetland in wetlands:
        records = list(
            WetlandMonitoringRecord.objects
            .filter(wetland=wetland)
            .order_by('-year')[:2]
        )
        if not records:
            continue

        current_record = records[0]
        previous_record = records[1] if len(records) > 1 else None

        ndvi_current = current_record.ndvi_mean
        ndvi_previous = previous_record.ndvi_mean if previous_record else None
        ndvi_change_pct = _safe_pct_change(ndvi_previous, ndvi_current)
        ndvi_decline_pct = abs(ndvi_change_pct) if ndvi_change_pct is not None and ndvi_change_pct < 0 else 0.0
        ndvi_year_span = _year_span_text(previous_record.year if previous_record else None, current_record.year)

        bsi_current = current_record.bsi_mean
        bsi_previous = previous_record.bsi_mean if previous_record else None
        bsi_change_pct = _safe_pct_change(bsi_previous, bsi_current)
        bsi_increase_pct = bsi_change_pct if bsi_change_pct is not None and bsi_change_pct > 0 else 0.0
        bsi_year_span = _year_span_text(previous_record.year if previous_record else None, current_record.year)

        metadata = wetland.metadata or {}
        lst_current = metadata.get('latest_lst_c')
        lst_previous = metadata.get('previous_lst_c')
        if lst_current is not None and lst_previous is not None:
            lst_increase = float(lst_current) - float(lst_previous)
        else:
            lst_increase = None
        lst_year_span = _year_span_text(previous_record.year if previous_record else None, current_record.year)

        if ndvi_decline_pct >= 20:
            severity = 'critical' if ndvi_decline_pct >= 35 else 'warning'
            alerts.append({
                'severity': severity,
                'title': f'NDVI decline threshold crossed at {wetland.name}',
                'desc': f'NDVI declined by {ndvi_decline_pct:.1f}% {ndvi_year_span} (threshold: 20%).',
                'wetland_id': wetland.id,
                'trigger_year': current_record.year,
                'site': wetland.name,
                'district': _wetland_location_label(wetland),
                'category': 'Rule: NDVI decline',
                'source': 'Rule-based threshold engine',
                'time': _relative_time_from_year(current_record.year),
                'date': date(current_record.year, 1, 1).isoformat(),
                'unread': True,
                'score': round(ndvi_decline_pct / 100.0, 3),
                'thresholds': {'ndvi_decline_pct': round(ndvi_decline_pct, 2), 'trigger_pct': 20},
            })

        if bsi_current is not None and bsi_current >= 0.18:
            severity = 'critical' if bsi_current >= 0.25 else 'warning'
            alerts.append({
                'severity': severity,
                'title': f'BSI threshold crossed at {wetland.name}',
                'desc': f'Current BSI is {bsi_current:.3f}; compared across {bsi_year_span} (warning threshold: 0.18).',
                'wetland_id': wetland.id,
                'trigger_year': current_record.year,
                'site': wetland.name,
                'district': _wetland_location_label(wetland),
                'category': 'Rule: BSI',
                'source': 'Rule-based threshold engine',
                'time': _relative_time_from_year(current_record.year),
                'date': date(current_record.year, 1, 1).isoformat(),
                'unread': True,
                'score': round(float(bsi_current), 3),
                'thresholds': {
                    'bsi_current': round(float(bsi_current), 3),
                    'bsi_increase_pct': round(float(bsi_increase_pct), 2),
                    'trigger': 0.18,
                },
            })

        if lst_current is not None and float(lst_current) >= 26:
            severity = 'critical' if float(lst_current) >= 30 else 'warning'
            alerts.append({
                'severity': severity,
                'title': f'LST threshold crossed at {wetland.name}',
                'desc': f'LST is {float(lst_current):.1f}°C; compared across {lst_year_span} (warning threshold: 26°C).',
                'wetland_id': wetland.id,
                'trigger_year': current_record.year,
                'site': wetland.name,
                'district': _wetland_location_label(wetland),
                'category': 'Rule: LST',
                'source': 'Rule-based threshold engine',
                'time': _relative_time_from_year(current_record.year),
                'date': date(current_record.year, 1, 1).isoformat(),
                'unread': True,
                'score': round(float(lst_current) / 40.0, 3),
                'thresholds': {
                    'lst_current_c': round(float(lst_current), 2),
                    'lst_increase_c': round(float(lst_increase), 2) if lst_increase is not None else None,
                    'trigger_c': 26,
                },
            })

        composite_alert = _compose_composite_alert(
            wetland,
            current_record,
            {
                'ndvi_decline_pct': ndvi_decline_pct,
                'bsi_current': bsi_current,
                'bsi_increase_pct': bsi_increase_pct,
                'lst_current': float(lst_current) if lst_current is not None else None,
                'lst_increase': float(lst_increase) if lst_increase is not None else None,
                'erosion_risk': current_record.erosion_risk,
                'ndvi_year_span': ndvi_year_span,
                'bsi_year_span': bsi_year_span,
                'lst_year_span': lst_year_span,
            }
        )
        if composite_alert:
            alerts.append(composite_alert)

    def _priority(alert):
        sev_order = {'critical': 0, 'warning': 1, 'info': 2, 'resolved': 3}
        # Community field reports beat rule-based alerts at the same severity (0 < 1)
        source_order = 0 if alert.get('source') == 'community_input' else 1
        return (sev_order.get(alert.get('severity', 'info'), 2), source_order, -(alert.get('score') or 0))

    alerts.sort(key=_priority)
    for idx, alert in enumerate(alerts, 1):
        alert['id'] = idx

    return _apply_read_state(request, alerts)


@csrf_exempt
def mark_early_warning_alert_read(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    alert_key = None
    if request.content_type and request.content_type.startswith('application/json'):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)
        alert_key = payload.get('alert_key')
    else:
        alert_key = request.POST.get('alert_key')

    if not alert_key:
        return JsonResponse({'success': False, 'error': 'alert_key is required'}, status=400)

    saved = _save_read_alert_key(request, alert_key)
    alerts = _build_early_warning_alerts(request)
    unread_count = sum(1 for alert in alerts if alert.get('unread', True))
    return JsonResponse({'success': True, 'saved': saved, 'unread_count': unread_count})


def api_early_warning_alerts(request):
    """Return rule-based and composite early warning alerts."""
    try:
        return JsonResponse({'alerts': _build_early_warning_alerts(request)})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)
