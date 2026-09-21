from core.common.errors import CustomError


class InvalidAudioSignalError(CustomError):
    code = 422
    error_code = "ONSET__INVALID_AUDIO_SIGNAL"
    message = "분석할 수 없는 음성 신호입니다."


class InvalidOnsetCriteriaError(CustomError):
    code = 500
    error_code = "ONSET__INVALID_CRITERIA"
    message = "onset 판정 기준 설정이 올바르지 않습니다."
