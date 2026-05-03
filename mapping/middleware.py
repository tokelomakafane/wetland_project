from django.shortcuts import redirect
from django.urls import reverse


class LoginRequiredMiddleware:
    """Redirect unauthenticated users to login for all non-exempt URLs."""

    EXEMPT_PREFIXES = ('/static/', '/media/', '/admin/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Always allow static/media/admin through
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return self.get_response(request)

        # Allow login and root redirect
        try:
            login_url = reverse('mapping:login')
            index_url = reverse('mapping:index')
        except Exception:
            return self.get_response(request)

        if path in (login_url, index_url):
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return redirect('mapping:login')

        return self.get_response(request)
