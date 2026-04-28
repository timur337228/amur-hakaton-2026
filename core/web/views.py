from __future__ import annotations

from django.conf import settings
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse


def dashboard(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "web/index.html",
        {
            "budget_api_base_url": settings.BUDGET_API_BASE_URL,
            "budget_deploy_mode": settings.BUDGET_DEPLOY_MODE,
        },
    )
