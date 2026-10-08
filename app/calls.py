import numpy as np
from numpy.typing import NDArray


def detect_calls(
    audio: NDArray[np.float64],
    sample_rate: int,
    *,
    max_silence_ms: float = 100.0,
) -> list[tuple[int, int]]:
    if audio.size == 0:
        return []

    # 10 ms frame별 RMS dBFS
    frame_samples = round(sample_rate * 10.0 / 1000)
    frame_starts = np.arange(0, audio.size, frame_samples)
    frame_sizes = np.minimum(frame_samples, audio.size - frame_starts)
    energies = np.add.reduceat(audio * audio, frame_starts)
    with np.errstate(divide="ignore"):
        rms_dbfs = 10 * np.log10(energies / frame_sizes)

    active_frames = np.flatnonzero(rms_dbfs >= -39.0)
    if active_frames.size == 0:
        return []

    # max_silence_ms 이하 무음은 한 울음으로 연결
    gap_lengths = frame_starts[active_frames[1:]] - (
        frame_starts[active_frames[:-1]] + frame_sizes[active_frames[:-1]]
    )
    call_frame_ids = np.split(
        active_frames,
        np.flatnonzero(gap_lengths > round(sample_rate * max_silence_ms / 1000)) + 1,
    )

    min_call_samples = round(sample_rate * 30.0 / 1000)
    return [
        (
            int(frame_starts[frame_ids[0]]),
            int(frame_starts[frame_ids[-1]] + frame_sizes[frame_ids[-1]]),
        )
        for frame_ids in call_frame_ids
        if frame_sizes[frame_ids].sum() >= min_call_samples
    ]


def count_chirps(
    audio: NDArray[np.float64], sample_rate: int, calls: list[tuple[int, int]]
) -> int:
    hann_window = np.hanning(1024)
    frequencies = np.fft.rfftfreq(1024, 1 / sample_rate)
    search_band = (frequencies >= 250.0) & (frequencies <= 8000.0)

    chirp_count = 0
    for start, end in calls:
        segment = audio[start:end]
        if segment.size < 1024:
            segment = np.pad(segment, (0, 1024 - segment.size))

        # 1,024 샘플 window별 파워 스펙트럼의 합
        window_starts = np.arange(0, segment.size - 1024 + 1, 160)
        windows = segment[window_starts[:, None] + np.arange(1024)[None, :]]
        window_powers = np.abs(np.fft.rfft(windows * hann_window, axis=1)) ** 2
        power_spectrum = window_powers.sum(axis=0)

        peak_frequency = frequencies[search_band][power_spectrum[search_band].argmax()]
        if peak_frequency >= 4600.0:
            chirp_count += 1

    return chirp_count
