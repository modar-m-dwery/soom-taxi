import 'package:equatable/equatable.dart';

import 'json.dart';

/// تقدّم السائق نحو حافز: «أنجزت 12 من 30 — بقي 18 لعشرة ليترات».
class IncentiveProgress extends Equatable {
  const IncentiveProgress({
    required this.programId,
    required this.name,
    required this.targetTrips,
    required this.completedTrips,
    required this.remainingTrips,
    required this.rewardLabel,
    required this.earned,
    this.description = '',
    this.period = 'week',
    this.awardStatus,
  });

  final int programId;
  final String name;
  final String description;
  final String period;
  final int targetTrips;
  final int completedTrips;
  final int remainingTrips;
  final String rewardLabel;
  final bool earned;

  /// `pending` (بانتظار التسليم) أو `delivered`.
  final String? awardStatus;

  double get fraction =>
      targetTrips <= 0 ? 0 : (completedTrips / targetTrips).clamp(0, 1).toDouble();

  factory IncentiveProgress.fromJson(Json json) => IncentiveProgress(
        programId: readInt(json, 'program_id'),
        name: readString(json, 'name'),
        description: readString(json, 'description', fallback: ''),
        period: readString(json, 'period', fallback: 'week'),
        targetTrips: readInt(json, 'target_trips'),
        completedTrips: readInt(json, 'completed_trips'),
        remainingTrips: readInt(json, 'remaining_trips'),
        rewardLabel: readString(json, 'reward_label'),
        earned: readBool(json, 'earned'),
        awardStatus: readStringOrNull(json, 'award_status'),
      );

  @override
  List<Object?> get props => [programId, completedTrips, earned, awardStatus];
}
