from datetime import UTC, datetime

from google.protobuf.timestamp_pb2 import Timestamp

from buddybird.ai.v1 import onset_pb2, onset_pb2_grpc


def test_analyze_session_request_round_trip() -> None:
    captured_at = Timestamp()
    captured_at.FromDatetime(datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC))
    request = onset_pb2.AnalyzeSessionRequest(
        capture=onset_pb2.CaptureInput(
            capture_id="cap_01",
            s3_key="audio_capture/uid/capture/file/session.wav",
            captured_at=captured_at,
        )
    )

    parsed = onset_pb2.AnalyzeSessionRequest.FromString(request.SerializeToString())

    assert parsed.WhichOneof("message") == "capture"
    assert parsed.capture.s3_key == "audio_capture/uid/capture/file/session.wav"
    assert parsed.capture.captured_at.ToDatetime(tzinfo=UTC) == datetime(
        2026, 9, 17, 12, 0, 0, tzinfo=UTC
    )


def test_onset_service_exposes_analyze_session_stream() -> None:
    method = onset_pb2.DESCRIPTOR.services_by_name["OnsetService"].methods_by_name[
        "AnalyzeSession"
    ]

    assert method.client_streaming
    assert method.server_streaming
    assert hasattr(onset_pb2_grpc, "OnsetServiceServicer")
    assert hasattr(onset_pb2_grpc, "add_OnsetServiceServicer_to_server")
