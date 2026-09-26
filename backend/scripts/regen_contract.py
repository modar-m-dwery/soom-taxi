# -*- coding: utf-8 -*-
"""
يولّد مخطّط OpenAPI من الخادم ويكتبه في اختبار العقد لتطبيقات فلاتر.

    python scripts/regen_contract.py

شغّله بعد أيّ تغيير في serializers أو views أو urls، ثمّ من mobile/:
    cd packages/soum_core && flutter test test/contract_test.dart

اختبار العقد يقارن ما يرسله الخادم بما تقرؤه النماذج في soum_core؛ حقلٌ
يُحذف أو يُعاد تسميته يُكسر هناك قبل أن يُكسر عند الزبون.

الملفّ محفوظ بنهايات أسطر CRLF وبلا سطر أخير — كما كان — فلا يظهر في git
فرقٌ في كلّ سطر عند كلّ توليد.
"""
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
CONTRACT = BACKEND.parent / "mobile" / "packages" / "soum_core" / "test" / "contract" / "openapi.json"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "schema.json"
        call_command("spectacular", file=str(out), format="openapi-json")
        data = out.read_bytes()
    data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n").rstrip(b"\r\n")
    CONTRACT.write_bytes(data)
    print(f"✓ {CONTRACT.relative_to(BACKEND.parent)}")


if __name__ == "__main__":
    main()
