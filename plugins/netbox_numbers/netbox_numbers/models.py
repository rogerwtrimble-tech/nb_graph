from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse

from netbox.models import PrimaryModel

from .choices import NumberStatusChoices

E164 = RegexValidator(r'^\+[1-9]\d{6,14}$', 'Enter an E.164 number, e.g. +13125550100')


class TelephoneNumber(PrimaryModel):
    number = models.CharField(max_length=20, unique=True, validators=[E164])
    status = models.CharField(
        max_length=30, choices=NumberStatusChoices, default=NumberStatusChoices.STATUS_AVAILABLE
    )
    site = models.ForeignKey(
        to='dcim.Site', on_delete=models.PROTECT, related_name='telephone_numbers', blank=True, null=True
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant', on_delete=models.PROTECT, related_name='telephone_numbers', blank=True, null=True
    )
    interface = models.ForeignKey(
        to='dcim.Interface', on_delete=models.SET_NULL, related_name='telephone_numbers', blank=True, null=True
    )
    sip_username = models.CharField(max_length=100, blank=True)

    clone_fields = ('status', 'site', 'tenant')

    class Meta:
        ordering = ('number',)
        verbose_name = 'telephone number'
        verbose_name_plural = 'telephone numbers'

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse('plugins:netbox_numbers:telephonenumber', args=[self.pk])

    def get_status_color(self):
        return NumberStatusChoices.colors.get(self.status)

    def clean(self):
        super().clean()
        if self.interface_id and self.status == NumberStatusChoices.STATUS_AVAILABLE:
            raise ValidationError({'status': 'A number assigned to an interface cannot be "available".'})
