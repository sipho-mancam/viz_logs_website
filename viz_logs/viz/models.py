from django.db import models
import json

class VizData(models.Model):
    id = models.AutoField(primary_key=True)
    group_id = models.CharField(max_length=50, db_index=True)
    display_name = models.CharField(max_length=255, null=True, blank=True)
    time_on_air = models.FloatField(null=True, blank=True)
    time_on_camera = models.FloatField(null=True, blank=True)
    sponsor_logo_name = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    visibility_map = models.TextField(max_length=16383)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'viz_data'
        ordering = ['-created_at']
        managed = False  # Add this line

    def get_visibility_data(self):
        """Parse the JSON visibility map and return as dict"""
        try:
            j = json.loads(self.visibility_map)
            total = 0
            for key in j:
                total += j[key]
            if total > 0:
                for key in j:
                    j[key] = round((j[key] / total) * 100, 2)

            return j
        except json.JSONDecodeError:
            return {}

    def get_histogram_data(self):
        """Convert visibility map to histogram format for Chart.js"""
        visibility_data = self.get_visibility_data()
        # Sort by bin number
        sorted_bins = sorted(visibility_data.items(), key=lambda x: int(x[0]))
        return {
            'labels': [f"{int(bin_num) - 10} - {int(bin_num)-1 if int(bin_num) < 100 else 100} %" for bin_num, _ in sorted_bins],
            'values': [value for _, value in sorted_bins]
        }

    def __str__(self):
        return f"{self.display_name or self.group_id} - {self.sponsor_logo_name}"