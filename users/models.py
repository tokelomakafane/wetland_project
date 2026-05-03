from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('community_member', 'Community Member'),
        ('doe_officer', 'DOE Officer'),
        ('dma_officer', 'DMA Officer'),
        ('system_admin', 'System Admin'),
        ('nul_researcher', 'NUL Researcher'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='community_member')

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()}"

    @property
    def role_label(self):
        return self.get_role_display()
