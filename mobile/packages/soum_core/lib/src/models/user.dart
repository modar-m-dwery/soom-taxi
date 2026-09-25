import 'package:equatable/equatable.dart';

import 'enums.dart';
import 'json.dart';

class AppUser extends Equatable {
  const AppUser({
    required this.id,
    required this.phone,
    required this.name,
    required this.role,
    required this.isVerified,
    required this.isActive,
    this.createdAt,
  });

  final int id;
  final String phone;
  final String name;
  final UserRole role;
  final bool isVerified;
  final bool isActive;
  final DateTime? createdAt;

  bool get isDriver => role == UserRole.driver;

  factory AppUser.fromJson(Json json) => AppUser(
        id: readInt(json, 'id'),
        phone: readString(json, 'phone'),
        name: readString(json, 'name'),
        role: UserRole.from(readStringOrNull(json, 'role')),
        isVerified: readBool(json, 'is_verified'),
        isActive: readBool(json, 'is_active', fallback: true),
        createdAt: readDateOrNull(json, 'created_at'),
      );

  @override
  List<Object?> get props => [id, phone, name, role, isVerified, isActive];
}
