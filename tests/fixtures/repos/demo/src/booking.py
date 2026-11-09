"""Workshop booking service used by the library scenario starter."""


class BookingService:
    def __init__(self, capacity: int = 30) -> None:
        self.capacity = capacity
        self._bookings: dict[str, dict] = {}

    def request_booking(self, course_code: str, headcount: int, slot: str) -> dict:
        if headcount > self.capacity:
            raise ValueError("headcount exceeds room capacity")
        if slot in self._bookings:
            raise ValueError("slot already taken")
        record = {"course_code": course_code, "headcount": headcount, "slot": slot}
        self._bookings[slot] = record
        return record

    def cancel(self, slot: str) -> None:
        self._bookings.pop(slot, None)
