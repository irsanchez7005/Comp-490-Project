from django.db import models
from django.conf import settings

# Create your models here.
#This is for posts which belong to community app/side
class Post(models.Model):
    post_Id= models.BigAutoField(primary_key=True)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL,
                         on_delete=models.CASCADE, related_name="posts")
    post_title= models.CharField(max_length=200)
    description=models.TextField()
    date_created=models.DateTimeField(auto_now_add=True)
#
class Comment(models.Model):
    comment_Id=models.BigAutoField(primary_key=True)
    post=models.ForeignKey(Post,on_delete=models.CASCADE,related_name="comments")
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="comments")
    created_at=models.DateTimeField(auto_now_add=True)
    sport_type=models.CharField(max_length=50,blank=True)
    price=models.DecimalField(max_digits=10,decimal_places=2, null=True,blank=True)
    content=models.TextField()
    rating_score=models.FloatField(null=True,blank=True)

class SavedPost(models.Model):
    post=models.ForeignKey(Post, on_delete=models.CASCADE,related_name="savedPosts")
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="savedPosts")
    saved_at=models.DateField(auto_now_add=True)

