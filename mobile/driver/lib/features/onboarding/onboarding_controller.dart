/// التوثيق — الطريق من حساب زبون إلى سائق يعمل.
///
/// §6.1 في وثيقة المنتج: السائق لا يدخل المطابقة إلّا إذا اجتمعت أربعة
/// شروط — حساب فعّال غير موقوف، ومركبة فعّالة بسعة كافية، والوثائق الأربع
/// مرفوعة ومقبولة، ولا وثيقة منتهية الصلاحية.
///
/// وترتيب الخطوات مفروض من الخادم لا من الواجهة: ‏`/vehicles/` يحتاج
/// حسابًا بدور سائق، و`go-online` يحتاج الوثائق. عرضُ الخطوات بلا هذا
/// الترتيب يُنتج أخطاءً لا يفهمها السائق.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';

import '../../providers.dart';

enum OnboardingStep { becomeDriver, vehicle, documents, review, ready }

class OnboardingState {
  const OnboardingState({
    required this.step,
    this.vehicles = const [],
    this.documents = const [],
    this.isBusy = false,
    this.failure,
  });

  final OnboardingStep step;
  final List<Vehicle> vehicles;
  final List<DriverDocument> documents;
  final bool isBusy;
  final ApiException? failure;

  bool get hasActiveVehicle => vehicles.any((v) => v.active);

  /// الوثائق الأربع المطلوبة — من التعداد لا من عدّ ما رُفع: سائقٌ رفع
  /// ثلاثًا مرّتين ليس سائقًا اكتملت وثائقه.
  Map<DriverDocumentType, DriverDocument?> get byType => {
        for (final type in DriverDocumentType.values)
          type: documents.where((d) => d.type == type).firstOrNull,
      };

  bool get allApproved => DriverDocumentType.values.every((type) {
        final document = byType[type];
        return document != null &&
            document.status == DocumentStatus.approved &&
            !document.isExpired;
      });

  bool get anyPending =>
      documents.any((d) => d.status == DocumentStatus.pending);

  OnboardingState copyWith({
    OnboardingStep? step,
    List<Vehicle>? vehicles,
    List<DriverDocument>? documents,
    bool? isBusy,
    ApiException? failure,
    bool clearFailure = true,
  }) =>
      OnboardingState(
        step: step ?? this.step,
        vehicles: vehicles ?? this.vehicles,
        documents: documents ?? this.documents,
        isBusy: isBusy ?? this.isBusy,
        failure: clearFailure ? failure : (failure ?? this.failure),
      );
}

final onboardingControllerProvider =
    NotifierProvider<OnboardingController, OnboardingState>(
        OnboardingController.new);

class OnboardingController extends Notifier<OnboardingState> {
  @override
  OnboardingState build() {
    Future.microtask(refresh);
    return const OnboardingState(step: OnboardingStep.becomeDriver);
  }

  Soum get _soum => ref.read(soumProvider);

  Future<void> refresh() async {
    final user = ref.read(currentUserProvider);

    if (user != null && !user.isDriver) {
      state = state.copyWith(step: OnboardingStep.becomeDriver);
      return;
    }

    state = state.copyWith(isBusy: true);

    try {
      final vehicles = await _soum.driver.vehicles();
      final documents = await _soum.driver.documents();

      final next = OnboardingState(
        step: OnboardingStep.vehicle,
        vehicles: vehicles,
        documents: documents,
      );

      state = next.copyWith(step: _resolveStep(next));
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, failure: error);
    }
  }

  static OnboardingStep _resolveStep(OnboardingState snapshot) {
    if (!snapshot.hasActiveVehicle) return OnboardingStep.vehicle;
    if (snapshot.allApproved) return OnboardingStep.ready;
    if (snapshot.anyPending) return OnboardingStep.review;
    return OnboardingStep.documents;
  }

  Future<bool> becomeDriver() async {
    state = state.copyWith(isBusy: true);
    try {
      await _soum.auth.becomeDriver();
      // الدور تغيّر على الخادم: نعيد الإقلاع ليحمل المستخدمُ دورَه
      // الجديد، وإلّا بقي التطبيق يراه زبونًا حتّى الإقلاع التالي.
      await ref.read(bootControllerProvider.notifier).resumeAfterLogin();
      await refresh();
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, failure: error);
      return false;
    }
  }

  Future<bool> registerVehicle({
    required String type,
    required String make,
    required String model,
    required int year,
    required String color,
    required String plateNumber,
    required int seats,
  }) async {
    state = state.copyWith(isBusy: true);
    try {
      final vehicle = await _soum.driver.registerVehicle(
        type: type,
        make: make,
        model: model,
        year: year,
        color: color,
        plateNumber: plateNumber,
        seats: seats,
      );

      // مركبةٌ مسجَّلة وغير فعّالة لا تُدخل المطابقة. التفعيل هنا لا في
      // شاشة أخرى: السائق سجّلها ليعمل بها.
      if (!vehicle.active) {
        await _soum.driver.activateVehicle(vehicle.id);
      }

      await refresh();
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, failure: error);
      return false;
    }
  }

  Future<bool> uploadDocument({
    required DriverDocumentType type,
    required String filePath,
    DateTime? expiresAt,
  }) async {
    state = state.copyWith(isBusy: true);
    try {
      await _soum.driver.uploadDocument(
        type: type,
        filePath: filePath,
        expiresAt: expiresAt,
      );
      await refresh();
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, failure: error);
      return false;
    }
  }
}
