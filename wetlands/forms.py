from django import forms
from mapping.models import Wetland, WetlandMonitoringRecord
import json


class WetlandForm(forms.ModelForm):
    """
    Form for creating/editing wetlands.
    Accepts polygon geometry as GeoJSON (stored as JSON string, not spatial).
    """

    # GeoJSON geometry input (will be converted to geometry field)
    geojson_geometry = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
        help_text="GeoJSON FeatureCollection from map drawing tool"
    )

    class Meta:
        model = Wetland
        fields = [
            'name',
            'village',
            'description',
            'elevation_m',
            'uploaded_by',
            'metadata',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Straw New Wetland'
            }),
            'village': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Village or district name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Description of wetland characteristics'
            }),
            'elevation_m': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Elevation in meters'
            }),
            'uploaded_by': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your name or team name'
            }),
            'metadata': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': '{"species": "...", "notes": "..."}'
            }),
        }

    def clean_metadata(self):
        """Validate JSON metadata."""
        metadata = self.cleaned_data.get('metadata')
        if metadata:
            try:
                json.loads(metadata)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON in metadata field")
        return metadata

    def clean_geojson_geometry(self):
        """Validate GeoJSON geometry (store as JSON string)."""
        geojson_str = self.cleaned_data.get('geojson_geometry')
        if not geojson_str:
            raise forms.ValidationError("Wetland boundary is required. Please draw a polygon on the map.")

        try:
            geojson = json.loads(geojson_str)

            # Extract geometry from FeatureCollection or Feature
            if geojson.get('type') == 'FeatureCollection':
                if not geojson.get('features'):
                    raise ValueError("No features in FeatureCollection")
                geometry = geojson['features'][0]['geometry']
            elif geojson.get('type') == 'Feature':
                geometry = geojson['geometry']
            else:
                geometry = geojson

            # Only accept Polygon or MultiPolygon
            if geometry['type'] not in ['Polygon', 'MultiPolygon']:
                raise ValueError("Geometry must be a Polygon or MultiPolygon")

            # Validate JSON structure has coordinates
            if not geometry.get('coordinates'):
                raise ValueError("Geometry missing coordinates")

            # Return as JSON string (not GEOS object)
            return json.dumps(geometry)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise forms.ValidationError(f"Invalid geometry: {str(e)}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Geometry is already JSON string from clean_geojson_geometry
        instance.geometry = self.cleaned_data['geojson_geometry']
        if commit:
            instance.save()
        return instance


class WetlandFilterForm(forms.Form):
    """Form for filtering and searching wetlands."""

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name or village'
        })
    )

    village = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by village'
        })
    )

    status = forms.ChoiceField(
        required=False,
        choices=[('', '-- All Status --')] + Wetland.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    risk_level = forms.ChoiceField(
        required=False,
        choices=[('', '-- All Risk Levels --')] + Wetland.RISK_LEVEL_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    source = forms.ChoiceField(
        required=False,
        choices=[('', '-- All Sources --')] + Wetland.source.field.choices,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    min_area_ha = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min area (ha)'
        })
    )

    max_area_ha = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Max area (ha)'
        })
    )


class BulkWetlandUploadForm(forms.Form):
    """Form for bulk uploading wetlands from GeoJSON or Shapefile."""

    FILE_FORMAT_CHOICES = [
        ('geojson', 'GeoJSON (.geojson or .json)'),
        ('shapefile', 'Shapefile (.shp)'),
        ('kml', 'KML (.kml)'),
    ]

    file_format = forms.ChoiceField(
        choices=FILE_FORMAT_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.geojson,.json,.shp,.kml'
        })
    )

    source = forms.ChoiceField(
        choices=[('', '-- Select --')] + Wetland.source.field.choices,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    uploaded_by = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your name or team'
        })
    )

    overwrite_existing = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Check to update existing wetlands with same names"
    )


class MonitoringRecordForm(forms.ModelForm):
    """Form for creating monitoring records (usually auto-populated from EE)."""

    class Meta:
        model = WetlandMonitoringRecord
        fields = [
            'year',
            'season',
            'bsi_mean',
            'ndvi_mean',
            'slope_mean',
            'erosion_risk',
            'risk_class',
            'cloud_cover',
            'data_quality',
            'notes',
        ]
        widgets = {
            'year': forms.NumberInput(attrs={'class': 'form-control'}),
            'season': forms.Select(attrs={'class': 'form-control'}),
            'bsi_mean': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ndvi_mean': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'slope_mean': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'erosion_risk': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'risk_class': forms.Select(attrs={'class': 'form-control'}),
            'cloud_cover': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'data_quality': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
