from src.booking import BookingService


def test_request_booking_success():
    service = BookingService(capacity=30)
    result = service.request_booking("COMP3613", 25, "2026-11-10T10:00")
    assert result["course_code"] == "COMP3613"


def test_rejects_over_capacity():
    service = BookingService(capacity=10)
    try:
        service.request_booking("COMP3613", 12, "2026-11-10T10:00")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "capacity" in str(exc)
