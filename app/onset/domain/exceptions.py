class InvalidAudioSignalError(ValueError):
    """분석할 수 없는 입력 오디오. 모델 장애가 아니므로 헬스체크의 추론 실패로 세지 않는다."""

    def __init__(self, *, detail: object) -> None:
        super().__init__(f"분석할 수 없는 음성 신호입니다: {detail}")


class InvalidOnsetCriteriaError(ValueError):
    def __init__(self, *, detail: object) -> None:
        super().__init__(f"onset 판정 기준 설정이 올바르지 않습니다: {detail}")
