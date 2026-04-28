from datetime import date

from django.http import JsonResponse
from django.utils import timezone

from mapping.models import Wetland, WetlandMonitoringRecord


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


def _compose_composite_alert(wetland, current_record, metrics):
    ndvi_decline_pct = metrics.get('ndvi_decline_pct')
    bsi_current = metrics.get('bsi_current')
    bsi_increase_pct = metrics.get('bsi_increase_pct')
    lst_current = metrics.get('lst_current')
    lst_increase = metrics.get('lst_increase')
    erosion_risk = metrics.get('erosion_risk')

    score = 0.0
    reasons = []
    warning_rules = 0
    critical_rules = 0

    if ndvi_decline_pct is not None:
        if ndvi_decline_pct >= 35:
            score += 0.35
            reasons.append(f'NDVI declined by {ndvi_decline_pct:.1f}%')
            critical_rules += 1
        elif ndvi_decline_pct >= 20:
            score += 0.25
            reasons.append(f'NDVI declined by {ndvi_decline_pct:.1f}%')
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
            reasons.append(f'BSI increased by {bsi_increase_pct:.1f}%')
            warning_rules += 1
        elif bsi_increase_pct >= 10:
            score += 0.10
            reasons.append(f'BSI increased by {bsi_increase_pct:.1f}%')

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
        reasons.append(f'LST increased by {lst_increase:.1f}°C')
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
        'site': wetland.name,
        'district': wetland.district or 'Unknown',
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


def _build_early_warning_alerts():
    alerts = []

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

        bsi_current = current_record.bsi_mean
        bsi_previous = previous_record.bsi_mean if previous_record else None
        bsi_change_pct = _safe_pct_change(bsi_previous, bsi_current)
        bsi_increase_pct = bsi_change_pct if bsi_change_pct is not None and bsi_change_pct > 0 else 0.0

        metadata = wetland.metadata or {}
        lst_current = metadata.get('latest_lst_c')
        lst_previous = metadata.get('previous_lst_c')
        if lst_current is not None and lst_previous is not None:
            lst_increase = float(lst_current) - float(lst_previous)
        else:
            lst_increase = None

        if ndvi_decline_pct >= 20:
            severity = 'critical' if ndvi_decline_pct >= 35 else 'warning'
            alerts.append({
                'severity': severity,
                'title': f'NDVI decline threshold crossed at {wetland.name}',
                'desc': f'NDVI declined by {ndvi_decline_pct:.1f}% (threshold: 20%).',
                'site': wetland.name,
                'district': wetland.district or 'Unknown',
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
                'desc': f'Current BSI is {bsi_current:.3f} (warning threshold: 0.18).',
                'site': wetland.name,
                'district': wetland.district or 'Unknown',
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
                'desc': f'LST is {float(lst_current):.1f}°C (warning threshold: 26°C).',
                'site': wetland.name,
                'district': wetland.district or 'Unknown',
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
            }
        )
        if composite_alert:
            alerts.append(composite_alert)

    def _priority(alert):
        order = {'critical': 0, 'warning': 1, 'info': 2, 'resolved': 3}
        return (order.get(alert.get('severity', 'info'), 2), -(alert.get('score') or 0))

    alerts.sort(key=_priority)
    for idx, alert in enumerate(alerts, 1):
        alert['id'] = idx

    return alerts


def api_early_warning_alerts(request):
    """Return rule-based and composite early warning alerts."""
    try:
        return JsonResponse({'alerts': _build_early_warning_alerts()})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)
