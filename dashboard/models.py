from django.db import models


# Create your models here.
class Notification(models.Model):
    title = models.CharField(max_length=255, verbose_name="Titre")
    message = models.TextField(verbose_name="Message")

    notification_type = models.CharField(
        max_length=20,
        choices=(
            ('info', 'Information'),
            ('success', 'Succès'),
            ('warning', 'Avertissement'),
            ('error', 'Erreur'),
        ),
        default='info', verbose_name="Type"
    )
    channel = models.CharField(
        verbose_name="Canal d'envoie", 
        choices={
            'email': 'Email'
        },
        default='email',
        max_length=64
    )

    image = models.ImageField(upload_to="notification/images/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    queued = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    def delete(self, *args, **kwargs):
        self.image.delete()
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']


class Message(models.Model):
    subject = models.CharField(max_length=255, verbose_name="Sujet")
    message = models.TextField(verbose_name="Message")

    message_type = models.CharField(
        max_length=20,
        choices=(
            ('info', 'Information'),
            ('success', 'Succès'),
            ('warning', 'Avertissement'),
            ('error', 'Erreur'),
        ),
        default='info',
        verbose_name="Type"
    )
    channel = models.CharField(
        verbose_name="Canal d'envoie", 
        choices={
            'email': 'Email'
        },
        default='email',
        max_length=64
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    queued = models.BooleanField(default=False)

    def __str__(self):
        return self.subject

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ['-created_at']

