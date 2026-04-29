from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import datetime
import json


class Wetland(models.Model):
    """
    Model to store wetland polygons and metadata.
    Supports both static historical wetlands and newly mapped wetlands.
    
    NOTE: Uses JSON geometry (GeoJSON) instead of spatial database for simplicity.
    All polygon features still work, but no spatial queries (not needed).
    """
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('monitoring', 'Under Monitoring'),
        ('archived', 'Archived'),
    ]
    
    RISK_LEVEL_CHOICES = [
        ('low', 'Low Risk'),
        ('moderate', 'Moderate Risk'),
        ('high', 'High Risk'),
        ('unknown', 'Unknown'),
    ]
    
    # Basic identification
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique name for the wetland (e.g., 'Straw New Wetland')"
    )
    village = models.CharField(
        max_length=255,
        blank=True,
        help_text="Village or district where wetland is located"
    )
    description = models.TextField(blank=True, null=True)
    
    # Geometry & boundaries (stored as GeoJSON string)
    geometry = models.TextField(
        help_text="GeoJSON geometry of the wetland boundary"
    )
    area_ha = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.01)],
        help_text="Area in hectares (calculated from geometry)"
    )
    elevation_m = models.IntegerField(
        null=True,
        blank=True,
        help_text="Average elevation in meters"
    )
    
    # Monitoring metadata
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='monitoring',
        help_text="Current monitoring status"
    )
    risk_level = models.CharField(
        max_length=20,
        choices=RISK_LEVEL_CHOICES,
        default='unknown',
        help_text="Current erosion risk assessment"
    )
    
    # Dates
    date_discovered = models.DateField(
        auto_now_add=True,
        help_text="When this wetland was first added to system"
    )
    date_last_monitored = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last date monitoring data was computed"
    )
    
    # Upload & source tracking
    source = models.CharField(
        max_length=50,
        choices=[
            ('manual_drawing', 'Manually Drawn'),
            ('geojson_upload', 'GeoJSON Upload'),
            ('shapefile_upload', 'Shapefile Upload'),
            ('drone_survey', 'Drone Survey'),
            ('historical_static', 'Historical Static Data'),
        ],
        default='manual_drawing'
    )
    uploaded_by = models.CharField(
        max_length=255,
        blank=True,
        help_text="User or field team who mapped it"
    )
    
    # Version tracking
    version = models.IntegerField(default=1, help_text="Boundary version number")
    is_current = models.BooleanField(
        default=True,
        help_text="If False, this is a historical version"
    )
    
    # Additional properties (JSON for extensibility)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional properties (species, land use, notes)"
    )
    
    class Meta:
        ordering = ['-date_discovered']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['risk_level']),
            models.Index(fields=['village']),
            models.Index(fields=['date_discovered']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.village})"
    
    def save(self, *args, **kwargs):
        """Calculate area in hectares from GeoJSON geometry."""
        if self.geometry and isinstance(self.geometry, str):
            try:
                # Parse GeoJSON and calculate area using shapely
                from shapely.geometry import shape
                geom_data = json.loads(self.geometry) if isinstance(self.geometry, str) else self.geometry
                
                # Extract coordinates based on GeoJSON type
                if geom_data.get('type') == 'Feature':
                    geom_dict = geom_data['geometry']
                else:
                    geom_dict = geom_data
                
                # Use shapely to calculate area
                if geom_dict.get('type') == 'Polygon':
                    shapely_geom = shape(geom_dict)
                    # Area in square degrees; approximate to m² (varies by latitude)
                    # For Lesotho (around -30°): 1 degree ≈ 111 km
                    m_per_degree = 111000
                    area_m2 = shapely_geom.area * (m_per_degree ** 2)
                    self.area_ha = round(area_m2 / 10000, 2)  # Convert m² to hectares
                else:
                    self.area_ha = None
            except Exception as e:
                # If parsing fails, leave area_ha as is
                pass
        super().save(*args, **kwargs)


class CommunityInput(models.Model):
    """Field/community observations submitted for a wetland."""

    OBSERVATION_CHOICES = [
        ('grazing', 'Grazing'),
        ('erosion', 'Erosion'),
        ('invasive_species', 'Invasive species'),
    ]

    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('warning', 'Warning'),
        ('info', 'Info'),
        ('resolved', 'Resolved'),
    ]

    wetland = models.ForeignKey(
        Wetland,
        on_delete=models.CASCADE,
        related_name='community_inputs',
    )
    observation = models.CharField(max_length=32, choices=OBSERVATION_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    comments = models.TextField()
    submitted_by = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wetland', 'created_at']),
            models.Index(fields=['severity']),
        ]

    def __str__(self):
        return f"CommunityInput #{self.id} - {self.wetland.name} ({self.observation})"


class WetlandMonitoringRecord(models.Model):
    """
    Time-series records of monitoring metrics per wetland.
    Stores annual/seasonal erosion risk, vegetation indices, etc.
    """
    
    wetland = models.ForeignKey(
        Wetland,
        on_delete=models.CASCADE,
        related_name='monitoring_records'
    )
    
    # Temporal
    year = models.IntegerField(validators=[MinValueValidator(2013)])
    season = models.CharField(
        max_length=20,
        choices=[
            ('annual', 'Annual'),
            ('spring', 'Spring'),
            ('summer', 'Summer'),
            ('autumn', 'Autumn'),
            ('winter', 'Winter'),
        ],
        default='annual'
    )
    monitoring_date = models.DateField(auto_now_add=True)
    
    # Erosion metrics
    bsi_mean = models.FloatField(null=True, blank=True, help_text="Bare Soil Index mean")
    bsi_std = models.FloatField(null=True, blank=True, help_text="Bare Soil Index std dev")
    
    ndvi_mean = models.FloatField(null=True, blank=True, help_text="NDVI mean")
    ndvi_std = models.FloatField(null=True, blank=True, help_text="NDVI std dev")
    
    slope_mean = models.FloatField(null=True, blank=True, help_text="Slope mean (degrees)")
    
    # Risk classification
    erosion_risk = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        help_text="Erosion risk index (0=Low, 1=Moderate, 2=High)"
    )
    risk_class = models.CharField(
        max_length=20,
        choices=[('low', 'Low'), ('moderate', 'Moderate'), ('high', 'High')],
        null=True,
        blank=True
    )
    
    # Quality
    cloud_cover = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Cloud cover percentage in satellite data"
    )
    data_quality = models.CharField(
        max_length=20,
        choices=[
            ('good', 'Good'),
            ('fair', 'Fair'),
            ('poor', 'Poor'),
        ],
        default='good'
    )
    
    # Notes
    notes = models.TextField(blank=True, help_text="Field observations or issues")
    
    class Meta:
        ordering = ['-year', '-season']
        unique_together = [['wetland', 'year', 'season']]
        indexes = [
            models.Index(fields=['wetland', 'year']),
            models.Index(fields=['risk_class']),
        ]
    
    def __str__(self):
        return f"{self.wetland.name} - {self.year} {self.season}"


class WetlandBoundaryChange(models.Model):
    """
    Tracks version history of wetland boundaries.
    Allows rollback and comparison between edits.
    
    NOTE: Uses JSON geometry (GeoJSON) for compatibility with non-spatial database.
    """
    
    wetland = models.ForeignKey(
        Wetland,
        on_delete=models.CASCADE,
        related_name='boundary_changes'
    )
    
    old_geometry = models.TextField(
        null=True,
        blank=True,
        help_text="Previous geometry version (GeoJSON)"
    )
    new_geometry = models.TextField(help_text="Current geometry version (GeoJSON)")
    
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.CharField(max_length=255, blank=True)
    change_reason = models.CharField(
        max_length=255,
        choices=[
            ('initial_creation', 'Initial Creation'),
            ('field_verification', 'Field Verification'),
            ('drone_survey', 'Drone Survey Update'),
            ('erosion_boundary', 'Erosion Boundary Change'),
            ('manual_edit', 'Manual Edit'),
        ],
        default='manual_edit'
    )
    notes = models.TextField(blank=True)
    
    area_change_ha = models.FloatField(
        null=True,
        blank=True,
        help_text="Change in area (hectares)"
    )
    
    class Meta:
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.wetland.name} - v{self.wetland.version}"


class TimelapseJob(models.Model):
    """Async processing job for wetland timelapse frame generation and GIF export."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    wetland = models.ForeignKey(
        Wetland,
        on_delete=models.CASCADE,
        related_name='timelapse_jobs',
    )

    start_year = models.IntegerField(validators=[MinValueValidator(2013)])
    end_year = models.IntegerField(validators=[MinValueValidator(2013)])
    buffer_meters = models.IntegerField(default=100, validators=[MinValueValidator(0)])
    cloud_threshold = models.IntegerField(default=20, validators=[MinValueValidator(0), MaxValueValidator(100)])
    frames_per_second = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(10)])
    dimensions = models.IntegerField(default=300, validators=[MinValueValidator(64), MaxValueValidator(1024)])

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress_percent = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    error_message = models.TextField(blank=True)

    frame_urls = models.JSONField(default=list, blank=True)
    gif_relative_path = models.CharField(max_length=500, blank=True)
    gif_source_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['wetland', 'created_at']),
        ]

    def __str__(self):
        return f"TimelapseJob #{self.id} - {self.wetland.name} ({self.status})"
