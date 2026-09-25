class MatchingETAService:

    DEFAULT_SPEED_KMH = 30

    @classmethod
    def calculate_eta_minutes(
        cls,
        distance_km,
        average_speed_kmh=None,
    ):
        if distance_km <= 0:
            return 1

        if average_speed_kmh is None:
            average_speed_kmh = cls.DEFAULT_SPEED_KMH

        if average_speed_kmh <= 0:
            raise ValueError(
                "Average speed must be greater than zero."
            )

        minutes = (
            distance_km
            / average_speed_kmh
            * 60
        )

        return max(1, round(minutes))