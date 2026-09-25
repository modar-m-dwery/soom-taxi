"""
طبقة الرصد: معرّف حادثة واحد، سجلّات منظَّمة، رموز أخطاء، وأدوات تمنع
الابتلاع الصامت.

    from config.observability.context import bind, get_request_id
    from config.observability.safety import swallow, run_all, guarded
    from config.observability.errors import AppError
"""
