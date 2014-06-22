# forms.py

from django import forms
from richard.videos import models


class Speaker_Form(forms.ModelForm):
    class Meta:
        model = models.Speaker
        fields = (
                'name',
                )

class Video_Form(forms.ModelForm):
    class Meta:
        model = models.Video
        fields = (
                'title',
                'summary',
                )

