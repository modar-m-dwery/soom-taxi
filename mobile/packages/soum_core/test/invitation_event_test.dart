// -*- coding: utf-8 -*-
/// حدث `invitation.created` يحمل `invitation_id` لا `id`. النموذج يقرأ
/// الاثنين — وإلّا كان «اقبل» يضرب معرّفًا صفريًّا (العيب #34، وُجد على هاتف).
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

void main() {
  test('الدعوة من حدث المقبس تحمل معرّفها', () {
    final invitation = RideInvitation.fromJson({
      'invitation_id': 7,
      'ride_id': 191,
      'driver_id': 1,
      'status': 'pending',
      'ttl_seconds': 20,
      'expires_at': '2026-09-21T07:53:35Z',
      'quoted_fare': '7284.00',
    });
    expect(invitation.id, 7);
  });

  test('الدعوة من REST تحمل معرّفها كما هو', () {
    final invitation = RideInvitation.fromJson({'id': 3, 'ride_id': 1, 'status': 'pending'});
    expect(invitation.id, 3);
  });
}
