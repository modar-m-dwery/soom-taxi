from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from integrity import registry
from integrity.models import CaseStatus, RiskCase, RiskLevel, RiskProfile, RiskSignal, SignalStatus


@method_decorator(staff_member_required, name="dispatch")
class IntegrityDashboardView(View):
    """
    لوحة النزاهة: من يغشّ، بأيّ نمط، وما القضايا المفتوحة. كلّ صفّ يفتح
    ملفّ الحساب في الأدمن حيث القرار (تأكيد، إسقاط، تقييد، ملاحظة).
    """

    def get(self, request):
        try:
            days = max(1, min(int(request.GET.get("days", 7)), 90))
        except ValueError:
            days = 7
        since = timezone.now() - timedelta(days=days)

        signals = RiskSignal.objects.filter(created_at__gte=since, status=SignalStatus.ACTIVE)
        by_kind = list(
            signals.values("kind").annotate(n=Count("id"), accounts=Count("user", distinct=True))
            .order_by("-n")
        )
        peak = max((row["n"] for row in by_kind), default=0) or 1
        for row in by_kind:
            kind = registry.KINDS.get(row["kind"])
            row["label"] = kind.label if kind else row["kind"]
            row["advice"] = kind.advice if kind else ""
            row["pct"] = round(row["n"] * 100 / peak)

        levels = dict(
            RiskProfile.objects.order_by().values("level").annotate(n=Count("id"))
            .values_list("level", "n")
        )

        context = {
            "days": days,
            "kpis": {
                "open_cases": RiskCase.objects.filter(status=CaseStatus.OPEN).count(),
                "restricted": levels.get(RiskLevel.RESTRICTED, 0),
                "review": levels.get(RiskLevel.REVIEW, 0),
                "watch": levels.get(RiskLevel.WATCH, 0),
                "signals": signals.count(),
            },
            "by_kind": by_kind,
            "top_profiles": (
                RiskProfile.objects.exclude(level=RiskLevel.CLEAR)
                .select_related("user").order_by("-score")[:30]
            ),
            "open_cases": (
                RiskCase.objects.filter(status=CaseStatus.OPEN)
                .select_related("user").order_by("-score_at_open")[:30]
            ),
            "recent": signals.select_related("user", "counterpart").order_by("-created_at")[:40],
        }
        return render(request, "integrity/dashboard.html", context)
