import wave
import numpy as np
import os
from typing import Dict, List, Any


def analyze_audio_energy(audio_path: str, window_seconds: float = 0.5) -> Dict[str, Any]:
    """
    Analyze mono or stereo 16-bit PCM WAV audio to detect volume/energy spikes,
    laughter, emotional excitement, or shouting.
    Returns:
      - timeline: downsampled energy profile (normalized 0.0 to 1.0)
      - peaks: detected time ranges with high energy
      - mean_energy: overall average energy
      - max_energy: maximum energy observed
    """
    if not os.path.exists(audio_path):
        return {"timeline": [], "peaks": [], "mean_energy": 0.0, "max_energy": 0.0, "duration": 0.0}

    try:
        with wave.open(audio_path, 'rb') as wav_file:
            n_channels = wav_file.getnchannels()
            sampwidth = wav_file.getsampwidth()
            framerate = wav_file.getframerate()
            n_frames = wav_file.getnframes()

            if n_frames == 0 or framerate == 0:
                return {"timeline": [], "peaks": [], "mean_energy": 0.0, "max_energy": 0.0, "duration": 0.0}

            duration = n_frames / float(framerate)
            raw_data = wav_file.readframes(n_frames)

        # Parse 16-bit PCM audio samples
        if sampwidth == 2:
            dtype = np.int16
        elif sampwidth == 4:
            dtype = np.int32
        else:
            dtype = np.int16

        samples = np.frombuffer(raw_data, dtype=dtype)
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1)

        samples = samples.astype(np.float32)

        # Compute sliding-window RMS energy
        window_size = int(framerate * window_seconds)
        if window_size <= 0:
            window_size = 8000

        n_windows = len(samples) // window_size
        if n_windows == 0:
            return {"timeline": [], "peaks": [], "mean_energy": 0.0, "max_energy": 0.0, "duration": duration}

        trimmed_samples = samples[:n_windows * window_size].reshape(n_windows, window_size)
        rms_energies = np.sqrt(np.mean(trimmed_samples ** 2, axis=1))

        # Smooth energy profile
        if len(rms_energies) >= 3:
            kernel_size = min(5, len(rms_energies))
            kernel = np.ones(kernel_size) / kernel_size
            smoothed_energies = np.convolve(rms_energies, kernel, mode='same')
        else:
            smoothed_energies = rms_energies

        max_e = float(np.max(smoothed_energies)) if len(smoothed_energies) > 0 else 1.0
        min_e = float(np.min(smoothed_energies)) if len(smoothed_energies) > 0 else 0.0
        range_e = max_e - min_e if max_e > min_e else 1.0

        # Normalized energy timeline (0.0 to 1.0)
        norm_energies = (smoothed_energies - min_e) / range_e

        # Detect high-energy peaks (e.g. > mean + 0.8 * std or > 75th percentile)
        mean_norm = float(np.mean(norm_energies))
        std_norm = float(np.std(norm_energies))
        threshold = min(0.9, mean_norm + 0.75 * std_norm)

        peaks: List[Dict[str, Any]] = []
        in_peak = False
        peak_start = 0.0
        peak_max_val = 0.0

        for idx, val in enumerate(norm_energies):
            t = idx * window_seconds
            if val >= threshold:
                if not in_peak:
                    in_peak = True
                    peak_start = t
                    peak_max_val = val
                else:
                    peak_max_val = max(peak_max_val, val)
            else:
                if in_peak:
                    in_peak = False
                    peak_end = t
                    if peak_end - peak_start >= 1.0:  # at least 1s
                        peaks.append({
                            "start": round(peak_start, 2),
                            "end": round(peak_end, 2),
                            "energy": round(float(peak_max_val), 3),
                            "description": f"Emotional / Loudness spike at {int(peak_start // 60):02d}:{int(peak_start % 60):02d}"
                        })

        if in_peak:
            peaks.append({
                "start": round(peak_start, 2),
                "end": round(duration, 2),
                "energy": round(float(peak_max_val), 3),
                "description": f"Emotional / Loudness spike at {int(peak_start // 60):02d}:{int(peak_start % 60):02d}"
            })

        # Downsample timeline for UI display (50 to 100 points)
        target_points = 80
        step = max(1, len(norm_energies) // target_points)
        downsampled_timeline = [
            {"time": round(i * window_seconds, 2), "energy": round(float(norm_energies[i]), 3)}
            for i in range(0, len(norm_energies), step)
        ]

        return {
            "duration": round(duration, 2),
            "timeline": downsampled_timeline,
            "peaks": peaks[:8],  # Top prominent peaks
            "mean_energy": round(mean_norm, 3),
            "max_energy": round(float(np.max(norm_energies)) if len(norm_energies) > 0 else 1.0, 3)
        }

    except Exception as e:
        print(f"[AudioAnalyzer] Error analyzing audio energy: {e}")
        return {"timeline": [], "peaks": [], "mean_energy": 0.0, "max_energy": 0.0, "duration": 0.0}


def get_segment_energy_score(start_time: float, end_time: float, audio_analysis: Dict[str, Any]) -> float:
    """
    Calculate an energy multiplier/score (0.0 to 1.0) for a given time segment.
    """
    if not audio_analysis or not audio_analysis.get("timeline"):
        return 0.5

    timeline = audio_analysis.get("timeline", [])
    relevant_points = [p["energy"] for p in timeline if start_time <= p["time"] <= end_time]
    if not relevant_points:
        return 0.5

    avg_e = float(np.mean(relevant_points))
    max_e = float(np.max(relevant_points))
    # Weighted average: 60% mean, 40% peak spike
    score = 0.6 * avg_e + 0.4 * max_e
    return round(float(np.clip(score, 0.0, 1.0)), 2)
