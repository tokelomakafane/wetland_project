import json
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from mapping.models import Wetland, CommunityInput, WetlandMonitoringRecord, WetlandBoundaryChange


class Command(BaseCommand):
    help = 'Seeds database with sample wetland data for development and testing'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting data seeding...'))

        # Sample wetland data with Lesotho coordinates
        wetlands_data = [
            {
                'name': 'Straw New Wetland',
                'village': 'Straw Village',
                'description': 'Recently mapped wetland in Straw area, showing signs of erosion.',
                'geometry': self._create_polygon([
                    [28.5, -29.8],
                    [28.52, -29.8],
                    [28.52, -29.82],
                    [28.5, -29.82],
                    [28.5, -29.8],
                ]),
                'area_ha': 12.5,
                'elevation_m': 1850,
                'status': 'monitoring',
                'risk_level': 'high',
                'source': 'drone_survey',
                'uploaded_by': 'Field Team A',
            },
            {
                'name': 'Maseru Central Wetland',
                'village': 'Maseru',
                'description': 'Large wetland near Maseru with mixed land use.',
                'geometry': self._create_polygon([
                    [27.55, -29.61],
                    [27.58, -29.61],
                    [27.58, -29.64],
                    [27.55, -29.64],
                    [27.55, -29.61],
                ]),
                'area_ha': 35.8,
                'elevation_m': 1550,
                'status': 'active',
                'risk_level': 'moderate',
                'source': 'historical_static',
                'uploaded_by': 'Department of Environment',
            },
            {
                'name': 'Teyateyaneng Protected Wetland',
                'village': 'Teyateyaneng',
                'description': 'Protected wetland with conservation status.',
                'geometry': self._create_polygon([
                    [28.15, -29.75],
                    [28.18, -29.75],
                    [28.18, -29.78],
                    [28.15, -29.78],
                    [28.15, -29.75],
                ]),
                'area_ha': 22.3,
                'elevation_m': 1650,
                'status': 'active',
                'risk_level': 'low',
                'source': 'geojson_upload',
                'uploaded_by': 'Conservation NGO',
            },
            {
                'name': 'Mafeteng Eastern Wetland',
                'village': 'Mafeteng',
                'description': 'Seasonal wetland affected by grazing.',
                'geometry': self._create_polygon([
                    [28.08, -29.82],
                    [28.11, -29.82],
                    [28.11, -29.85],
                    [28.08, -29.85],
                    [28.08, -29.82],
                ]),
                'area_ha': 8.7,
                'elevation_m': 1920,
                'status': 'monitoring',
                'risk_level': 'moderate',
                'source': 'manual_drawing',
                'uploaded_by': 'Local Community',
            },
        ]

        # Create wetlands and seed related data
        for wetland_data in wetlands_data:
            wetland, created = Wetland.objects.get_or_create(
                name=wetland_data['name'],
                defaults=wetland_data
            )

            status = 'Created' if created else 'Already exists'
            self.stdout.write(self.style.SUCCESS(f'  ✓ {wetland.name} - {status}'))

            if created:
                # Seed community inputs
                self._seed_community_inputs(wetland)

                # Seed monitoring records
                self._seed_monitoring_records(wetland)

                # Seed boundary changes
                self._seed_boundary_changes(wetland)

        self.stdout.write(self.style.SUCCESS('✓ Data seeding completed successfully!'))

    def _create_polygon(self, coordinates):
        """Create a GeoJSON polygon."""
        return json.dumps({
            'type': 'Polygon',
            'coordinates': [coordinates]
        })

    def _seed_community_inputs(self, wetland):
        """Create sample community inputs for a wetland."""
        observations = [
            {
                'observation': 'grazing',
                'severity': 'warning',
                'comments': 'Observed livestock grazing on wetland margins.',
                'submitted_by': 'Farmer A',
            },
            {
                'observation': 'erosion',
                'severity': 'critical',
                'comments': 'Significant soil erosion on western bank.',
                'submitted_by': 'Community Leader',
            },
            {
                'observation': 'invasive_species',
                'severity': 'info',
                'comments': 'Some invasive plant species detected.',
                'submitted_by': 'Botanist',
            },
        ]

        for obs_data in observations:
            CommunityInput.objects.get_or_create(
                wetland=wetland,
                observation=obs_data['observation'],
                defaults={
                    'severity': obs_data['severity'],
                    'comments': obs_data['comments'],
                    'submitted_by': obs_data['submitted_by'],
                }
            )

    def _seed_monitoring_records(self, wetland):
        """Create sample monitoring records for multiple years."""
        base_date = datetime(2021, 1, 1)

        for year in range(2021, 2026):
            for season in ['annual', 'spring', 'summer']:
                risk_values = {
                    'low': (0.2, 'low'),
                    'moderate': (1.0, 'moderate'),
                    'high': (1.8, 'high'),
                }

                risk_key = wetland.risk_level
                erosion_risk, risk_class = risk_values.get(risk_key, (1.0, 'moderate'))

                WetlandMonitoringRecord.objects.get_or_create(
                    wetland=wetland,
                    year=year,
                    season=season,
                    defaults={
                        'monitoring_date': base_date + timedelta(days=365 * (year - 2021)),
                        'bsi_mean': 0.3 + (year - 2021) * 0.05,
                        'bsi_std': 0.1,
                        'ndvi_mean': 0.5 - (year - 2021) * 0.03,
                        'ndvi_std': 0.15,
                        'slope_mean': 15.5,
                        'erosion_risk': erosion_risk,
                        'risk_class': risk_class,
                        'cloud_cover': 15.0,
                        'data_quality': 'good',
                        'notes': f'Monitoring record for {year} {season} season.',
                    }
                )

    def _seed_boundary_changes(self, wetland):
        """Create sample boundary change history."""
        old_geom = json.dumps({
            'type': 'Polygon',
            'coordinates': [[
                [28.5, -29.8],
                [28.51, -29.8],
                [28.51, -29.81],
                [28.5, -29.81],
                [28.5, -29.8],
            ]]
        })

        WetlandBoundaryChange.objects.get_or_create(
            wetland=wetland,
            change_reason='initial_creation',
            defaults={
                'old_geometry': None,
                'new_geometry': wetland.geometry,
                'changed_by': wetland.uploaded_by,
                'notes': 'Initial boundary creation',
                'area_change_ha': None,
            }
        )

        if wetland.risk_level == 'high':
            WetlandBoundaryChange.objects.get_or_create(
                wetland=wetland,
                change_reason='erosion_boundary',
                defaults={
                    'old_geometry': old_geom,
                    'new_geometry': wetland.geometry,
                    'changed_by': 'Drone Team',
                    'notes': 'Boundary updated due to erosion',
                    'area_change_ha': -2.3,
                }
            )
