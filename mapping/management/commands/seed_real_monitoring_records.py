import json

from django.core.management.base import BaseCommand
from django.test.client import RequestFactory
from django.utils import timezone


class Command(BaseCommand):
    help = "Seed monitoring records from real Earth Engine outputs for the current wetlands."

    def handle(self, *args, **options):
        from mapping.models import Wetland, WetlandMonitoringRecord
        from wetlands.views import api_wetland_erosion_data

        years = tuple(range(2015, 2025))
        wetlands = Wetland.objects.filter(is_current=True).order_by('id')
        factory = RequestFactory()

        deleted_count, _ = WetlandMonitoringRecord.objects.all().delete()
        created_count = 0
        updated_count = 0
        skipped = []

        for wetland in wetlands:
            successful_payloads = []
            for year in years:
                request = factory.get(f'/api/wetlands/{wetland.id}/erosion/?year={year}')
                response = api_wetland_erosion_data(request, wetland.id)

                if response.status_code != 200:
                    continue

                payload = json.loads(response.content.decode('utf-8'))
                successful_payloads.append((year, payload))

            if not successful_payloads:
                skipped.append(f'{wetland.name}: no successful real-data years in {years[0]}-{years[-1]}')
                continue

            for year, payload in successful_payloads:
                risk_class = str(payload.get('risk_class', 'LOW')).strip().lower()
                if risk_class not in {'low', 'moderate', 'high'}:
                    risk_class = 'low'

                _, was_created = WetlandMonitoringRecord.objects.update_or_create(
                    wetland=wetland,
                    year=year,
                    season='annual',
                    defaults={
                        'ndvi_mean': payload.get('ndvi_mean'),
                        'bsi_mean': payload.get('bsi_mean'),
                        'slope_mean': payload.get('slope_mean'),
                        'erosion_risk': payload.get('erosion_risk'),
                        'risk_class': risk_class,
                        'cloud_cover': None,
                        'data_quality': 'good',
                        'notes': f'Real Earth Engine monitoring data seeded for {year}.',
                    },
                )
                if was_created:
                    created_count += 1
                else:
                    updated_count += 1

            wetland.date_last_monitored = timezone.now()
            wetland.save(update_fields=['date_last_monitored'])

        self.stdout.write(self.style.SUCCESS(
            f'Rebuilt monitoring records: deleted={deleted_count}, created={created_count}, updated={updated_count}, skipped={len(skipped)}'
        ))

        if skipped:
            self.stdout.write(self.style.WARNING('Skipped records:'))
            for item in skipped[:20]:
                self.stdout.write(f'  - {item}')
