from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import AccountRegisterForm

def createAccount(request):
    if request.method == "POST":
        form = AccountRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            username =form.cleaned_data.get('username')
            messages.success(request, 'Account created successfully!') 
            return redirect('login')        
    else:
        form = AccountRegisterForm()
    return render(request, 'accounts/register.html', {'form': form})
