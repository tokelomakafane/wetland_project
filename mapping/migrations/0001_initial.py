# Migration: Simplified non-spatial version (JSON geometry instead of GeoDjango)

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Wetland',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text="Unique name for the wetland (e.g., 'Straw New Wetland')", max_length=255, unique=True)),
                ('village', models.CharField(blank=True, help_text='Village or district where wetland is located', max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('geometry', models.TextField(help_text='GeoJSON geometry of the wetland boundary')),
                ('area_ha', models.FloatField(blank=True, help_text='Area in hectares (calculated from geometry)', null=True, validators=[django.core.validators.MinValueValidator(0.01)])),
                ('elevation_m', models.IntegerField(blank=True, help_text='Average elevation in meters', null=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive'), ('monitoring', 'Under Monitoring'), ('archived', 'Archived')], default='monitoring', help_text='Current monitoring status', max_length=20)),
                ('risk_level', models.CharField(choices=[('low', 'Low Risk'), ('moderate', 'Moderate Risk'), ('high', 'High Risk'), ('unknown', 'Unknown')], default='unknown', help_text='Current erosion risk assessment', max_length=20)),
                ('date_discovered', models.DateField(auto_now_add=True, help_text='When this wetland was first added to system')),
                ('date_last_monitored', models.DateTimeField(blank=True, help_text='Last date monitoring data was computed', null=True)),
                ('source', models.CharField(choices=[('manual_drawing', 'Manually Drawn'), ('geojson_upload', 'GeoJSON Upload'), ('shapefile_upload', 'Shapefile Upload'), ('drone_survey', 'Drone Survey'), ('historical_static', 'Historical Static Data')], default='manual_drawing', max_length=50)),
                ('uploaded_by', models.CharField(blank=True, help_text='User or field team who mapped it', max_length=255)),
                ('version', models.IntegerField(default=1, help_text='Boundary version number')),
                ('is_current', models.BooleanField(default=True, help_text='If False, this is a historical version')),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Additional properties (species, land use, notes)')),
            ],
            options={
                'ordering': ['-date_discovered'],
            },
        ),
        migrations.CreateModel(
            name='WetlandMonitoringRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.IntegerField(validators=[django.core.validators.MinValueValidator(2013)])),
                ('season', models.CharField(choices=[('annual', 'Annual'), ('spring', 'Spring'), ('summer', 'Summer'), ('autumn', 'Autumn'), ('winter', 'Winter')], default='annual', max_length=20)),
                ('monitoring_date', models.DateField(auto_now_add=True)),
                ('bsi_mean', models.FloatField(blank=True, help_text='Bare Soil Index mean', null=True)),
                ('bsi_std', models.FloatField(blank=True, help_text='Bare Soil Index std dev', null=True)),
                ('ndvi_mean', models.FloatField(blank=True, help_text='NDVI mean', null=True)),
                ('ndvi_std', models.FloatField(blank=True, help_text='NDVI std dev', null=True)),
                ('slope_mean', models.FloatField(blank=True, help_text='Slope mean (degrees)', null=True)),
                ('slope_std', models.FloatField(blank=True, help_text='Slope std dev', null=True)),
                ('erosion_risk', models.FloatField(blank=True, help_text='Computed erosion risk (0-2)', null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(2)])),
                ('risk_class', models.CharField(blank=True, choices=[('low', 'Low'), ('moderate', 'Moderate'), ('high', 'High')], max_length=20, null=True)),
                ('cloud_cover', models.FloatField(blank=True, help_text='Cloud cover percentage in satellite data', null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ('data_quality', models.CharField(choices=[('good', 'Good'), ('fair', 'Fair'), ('poor', 'Poor')], default='good', max_length=20)),
                ('notes', models.TextField(blank=True, help_text='Field observations or issues')),
                ('wetland', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='monitoring_records', to='mapping.wetland')),
            ],
            options={
                'ordering': ['-year', '-season'],
                'unique_together': {('wetland', 'year', 'season')},
            },
        ),
        migrations.CreateModel(
            name='WetlandBoundaryChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_geometry', models.TextField(blank=True, help_text='Previous geometry version (GeoJSON)', null=True)),
                ('new_geometry', models.TextField(help_text='Current geometry version (GeoJSON)')),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.CharField(blank=True, max_length=255)),
                ('change_reason', models.CharField(choices=[('initial_creation', 'Initial Creation'), ('field_verification', 'Field Verification'), ('drone_survey', 'Drone Survey Update'), ('erosion_boundary', 'Erosion Boundary Change'), ('manual_edit', 'Manual Edit')], default='manual_edit', max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('area_change_ha', models.FloatField(blank=True, help_text='Change in area (hectares)', null=True)),
                ('wetland', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='boundary_changes', to='mapping.wetland')),
            ],
            options={
                'ordering': ['-changed_at'],
            },
        ),
        # Add indexes
        migrations.AddIndex(
            model_name='wetland',
            index=models.Index(fields=['status'], name='mapping_wet_status_idx'),
        ),
        migrations.AddIndex(
            model_name='wetland',
            index=models.Index(fields=['risk_level'], name='mapping_wet_risk_idx'),
        ),
        migrations.AddIndex(
            model_name='wetland',
            index=models.Index(fields=['village'], name='mapping_wet_village_idx'),
        ),
        migrations.AddIndex(
            model_name='wetland',
            index=models.Index(fields=['date_discovered'], name='mapping_wet_date_idx'),
        ),
        migrations.AddIndex(
            model_name='wetlandmonitoringrecord',
            index=models.Index(fields=['wetland', 'year'], name='mapping_mon_wetland_year_idx'),
        ),
        migrations.AddIndex(
            model_name='wetlandmonitoringrecord',
            index=models.Index(fields=['risk_class'], name='mapping_mon_risk_idx'),
        ),
    ]
