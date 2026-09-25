import json

from django.contrib import admin, messages
from django.utils.html import format_html, format_html_join

from integrity.models import (
    CaseStatus,
    RiskCase,
    RiskLevel,
    RiskNote,
    RiskProfile,
    RiskSignal,
    SignalStatus,
)
from integrity.services.scoring import IntegrityService

LEVEL_COLORS = {
    RiskLevel.CLEAR: "#2C6E49",
    RiskLevel.WATCH: "#8A6D00",
    RiskLevel.REVIEW: "#B35C00",
    RiskLevel.RESTRICTED: "#B3261E",
}


def _signals_html(user, limit=30):
    rows = RiskSignal.objects.filter(user=user).order_by("-created_at")[:limit]
    if not rows:
        return "—"
    return format_html(
        "<ul>{}</ul>",
        format_html_join(
            "", "<li>{} — <b>{}</b> — وزن {} — {} — <code>{}</code></li>",
            (
                (
                    s.created_at.strftime("%Y-%m-%d %H:%M"), s.kind_label, s.weight,
                    s.get_status_display(), json.dumps(s.evidence, ensure_ascii=False),
                )
                for s in rows
            ),
        ),
    )


def _level_badge(level):
    color = LEVEL_COLORS.get(level, "#555")
    return format_html(
        '<b style="color:{}">{}</b>', color, RiskLevel(level).label if level else "—",
    )


@admin.register(RiskProfile)
class RiskProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user", "role", "score", "level_badge", "manual_badge",
        "signals_count", "last_signal_at",
    )
    list_filter = ("level", "manual_level", "user__role")
    search_fields = ("user__phone", "user__name")
    ordering = ("-score",)
    readonly_fields = (
        "user", "score", "level", "signals_count", "last_signal_at", "updated_at",
        "signals_list", "notes_list",
    )
    fields = (
        "user", "score", "level", "signals_count", "last_signal_at",
        "manual_level", "manual_until", "updated_at", "signals_list", "notes_list",
    )
    actions = ["whitelist_30_days", "restrict_manually", "clear_manual", "recompute"]

    @admin.display(description="آخر الإشارات")
    def signals_list(self, obj):
        return _signals_html(obj.user)

    @admin.display(description="الملاحظات (أضف من «الملاحظات»)")
    def notes_list(self, obj):
        notes = RiskNote.objects.filter(user=obj.user).select_related("author")[:30]
        if not notes:
            return "—"
        return format_html(
            "<ul>{}</ul>",
            format_html_join(
                "", "<li>{} — {}: {}</li>",
                (
                    (n.created_at.strftime("%Y-%m-%d %H:%M"), n.author or "النظام", n.text)
                    for n in notes
                ),
            ),
        )

    @admin.display(description="الدور")
    def role(self, obj):
        return obj.user.get_role_display() if hasattr(obj.user, "get_role_display") else ""

    @admin.display(description="المستوى المحسوب")
    def level_badge(self, obj):
        return _level_badge(obj.level)

    @admin.display(description="قرار الإدارة")
    def manual_badge(self, obj):
        if not obj.manual_active():
            return "—"
        until = f" حتّى {obj.manual_until:%Y-%m-%d}" if obj.manual_until else ""
        return format_html("{}{}", _level_badge(obj.manual_level), until)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and {"manual_level", "manual_until"} & set(form.changed_data):
            IntegrityService.add_note(
                obj.user,
                f"قرار إداريّ من صفحة الملفّ: {obj.get_manual_level_display() or 'بلا تجاوز'}.",
                author=request.user,
            )
            IntegrityService._invalidate_restricted_cache()

    @admin.action(description="علّمهم «سليم» 30 يومًا (إنذار معروف)")
    def whitelist_30_days(self, request, queryset):
        for profile in queryset:
            IntegrityService.set_manual_level(
                profile.user, RiskLevel.CLEAR, author=request.user, days=30,
            )
        self.message_user(request, f"عُلِّم {queryset.count()} حسابًا سليمًا.", messages.SUCCESS)

    @admin.action(description="قيّدهم بقرار إداريّ")
    def restrict_manually(self, request, queryset):
        for profile in queryset:
            IntegrityService.set_manual_level(profile.user, RiskLevel.RESTRICTED, author=request.user)
        self.message_user(request, f"قُيِّد {queryset.count()} حسابًا.", messages.WARNING)

    @admin.action(description="ألغِ قرار الإدارة (عُد إلى النقاط)")
    def clear_manual(self, request, queryset):
        for profile in queryset:
            IntegrityService.set_manual_level(profile.user, "", author=request.user)
        self.message_user(request, "أُلغيت القرارات.", messages.SUCCESS)

    @admin.action(description="أعد حساب النقاط الآن")
    def recompute(self, request, queryset):
        for profile in queryset:
            IntegrityService.recompute(profile.user)
        self.message_user(request, "أُعيد الحساب.", messages.SUCCESS)


@admin.register(RiskSignal)
class RiskSignalAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind_label", "user", "weight", "status", "counterpart", "ride")
    list_filter = ("status", "kind")
    search_fields = ("user__phone", "user__name", "counterpart__phone")
    readonly_fields = (
        "user", "kind", "weight", "evidence", "ride", "trip", "counterpart",
        "dedupe_key", "created_at",
    )
    fields = readonly_fields + ("status",)
    date_hierarchy = "created_at"
    actions = ["dismiss_selected"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="النوع")
    def kind_label(self, obj):
        return obj.kind_label

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "status" in form.changed_data:
            IntegrityService.recompute(obj.user)

    @admin.action(description="أسقطها (إنذار كاذب) وأعد الحساب")
    def dismiss_selected(self, request, queryset):
        users = {s.user for s in queryset.select_related("user")}
        queryset.update(status=SignalStatus.DISMISSED)
        for user in users:
            IntegrityService.add_note(user, "أسقط موظّف إشاراتٍ كإنذار كاذب.", author=request.user)
            IntegrityService.recompute(user)
        self.message_user(request, f"أُسقطت الإشارات لـ{len(users)} حسابًا.", messages.SUCCESS)


@admin.register(RiskCase)
class RiskCaseAdmin(admin.ModelAdmin):
    list_display = ("opened_at", "user", "status", "score_at_open", "current_score", "reason")
    list_filter = ("status",)
    search_fields = ("user__phone", "user__name", "reason")
    readonly_fields = (
        "user", "status", "reason", "score_at_open", "opened_at",
        "resolved_at", "resolved_by", "signals_summary",
    )
    fields = readonly_fields + ("resolution_note",)
    actions = ["confirm_fraud", "dismiss_false_alarm"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="النقاط الآن")
    def current_score(self, obj):
        profile = getattr(obj.user, "risk_profile", None)
        return profile.score if profile else 0

    @admin.display(description="الإشارات")
    def signals_summary(self, obj):
        return _signals_html(obj.user)

    @admin.action(description="أكّد الغش (يبقى مقيّدًا بقرار إداريّ)")
    def confirm_fraud(self, request, queryset):
        n = 0
        for case in queryset.filter(status=CaseStatus.OPEN):
            IntegrityService.resolve_case(case, CaseStatus.CONFIRMED, author=request.user)
            n += 1
        self.message_user(request, f"أُكّدت {n} قضيّة.", messages.WARNING)

    @admin.action(description="إنذار كاذب (أسقط الإشارات وعلّمه سليمًا 30 يومًا)")
    def dismiss_false_alarm(self, request, queryset):
        n = 0
        for case in queryset.filter(status=CaseStatus.OPEN):
            IntegrityService.resolve_case(case, CaseStatus.DISMISSED, author=request.user)
            n += 1
        self.message_user(request, f"رُفضت {n} قضيّة.", messages.SUCCESS)


@admin.register(RiskNote)
class RiskNoteAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "author", "short_text")
    search_fields = ("user__phone", "user__name", "text")
    readonly_fields = ("created_at", "author")
    autocomplete_fields = ("user",)

    @admin.display(description="الملاحظة")
    def short_text(self, obj):
        return obj.text[:90]

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)
