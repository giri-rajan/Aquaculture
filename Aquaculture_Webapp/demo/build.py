"""Edit the recorded takes into the 150 s demo video (1920x1080, 30 fps) with captions and narration."""
import glob
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
FPS = 30
SRC = {k: glob.glob(str(HERE / k / "*.webm"))[0] for k in "ABC"}
FONT = "/System/Library/Fonts/SFNS.ttf"

# Crops in the 1600x900 recording (x, y, w, h), all 16:9
FULL = (0, 0, 1600, 900)
MISSION = (500, 230, 1100, 619)
DIAG_TOP = (500, 60, 1100, 619)
DIAG_BOT = (500, 281, 1100, 619)
MAPZOOM = (0, 450, 800, 450)
ZONES = (40, 230, 1100, 619)
ASK = (250, 100, 1100, 619)
ALERTS = (500, 70, 1100, 619)

# (source, in, out, crop, speed)   speed 2 = time-lapse
SEGMENTS = [
    # Scene 1 (10 s)
    ("A", 1.6, 11.6, "push", 1),
    # Scene 2 (18 s)
    ("A", 12.1, 22.8, MISSION, 1),
    ("A", 24.4, 25.9, MISSION, 1),
    ("A", 29.0, 34.8, FULL, 1),
    # Scene 3 (10 s)
    ("A", 35.2, 45.2, FULL, 1),
    # Scene 4 (20 s): 30 s at 2x, then the source estimate at real speed
    ("A", 43.0, 73.0, FULL, 2),
    ("A", 73.0, 78.0, MAPZOOM, 1),
    # Scene 5 (20 s)
    ("A", 81.0, 87.6, DIAG_TOP, 1),
    ("A", 87.6, 92.8, DIAG_BOT, 1),
    ("A", 94.4, 97.6, FULL, 1),
    ("A", 98.4, 103.4, MAPZOOM, 1),
    # Scene 6 (12 s)
    ("A", 102.6, 108.6, FULL, 1),
    ("A", 108.6, 114.6, ZONES, 1),
    # Scene 7 (20 s)
    ("B", 3.6, 6.6, FULL, 1),
    ("B", 8.8, 20.2, ASK, 1),
    ("B", 21.4, 22.4, ASK, 1),
    ("B", 25.4, 30.0, ASK, 1),
    # Scene 8 (15 s): alerts, report, then the PDF pages
    ("B", 35.4, 42.4, ALERTS, 1),
    ("B", 43.6, 45.0, FULL, 1),
    ("B", 49.0, 50.6, FULL, 1),
    ("PDF1", 0, 2.5, None, 1),
    ("PDF2", 0, 2.5, None, 1),
    # Scene 9 (13 s)
    ("B", 55.6, 68.6, FULL, 1),
    # Scene 10 (12 s)
    ("C", 3.0, 15.0, "phone", 1),
]

CAPTIONS = [
    (1.0, 5.0, "Live  ·  simulated lake"),
    (11.0, 17.5, "Voice input (synthesized voice), transcribed by Gemini"),
    (22.0, 27.6, "Gemini Planner  ·  every leg checked to stay on water"),
    (28.6, 33.5, "Hidden scenario: the agents are told nothing"),
    (38.2, 52.8, "Time-lapse 2×  ·  boat at 16× demo speed"),
    (53.2, 57.8, "Source estimate (!)"),
    (58.4, 64.4, "Gemini fuses sensors + camera + CPCB criteria"),
    (69.9, 72.8, "Simulated camera frame"),
    (73.2, 77.8, "True hidden source (×) sits under the estimate (!)"),
    (78.4, 84.0, "Our LightGBM model  ·  TreeSHAP factors"),
    (94.2, 101.3, "Tamil question (synthesized voice), transcribed by Gemini"),
    (104.0, 109.6, "Answer grounded in live data  ·  tool calls shown"),
    (120.0, 124.8, "PDF: stored-data tables + Gemini narrative"),
    (125.4, 131.0, "Simulator results, not field trials"),
    (138.4, 143.0, "Phone  ·  Hindi  ·  dark theme"),
]

# Narration and the two clips that were fed to the microphone, as (file, start in output seconds, tempo)
AUDIO = [
    ("vo/s1.aiff", 0.15, 1.1),
    ("vo/s2a.aiff", 10.1, 1.0),
    ("cmd.wav", 11.5, 1.0),
    ("vo/s2b.aiff", 18.1, 1.0),
    ("vo/s3.aiff", 28.4, 1.0),
    ("vo/s4.aiff", 38.5, 1.0),
    ("vo/s5.aiff", 58.3, 1.0),
    ("vo/s6.aiff", 78.4, 1.0),
    ("vo/s7a.aiff", 90.1, 1.0),
    ("ta.wav", 94.55, 1.0),
    ("vo/s7b.aiff", 101.6, 1.0),
    ("vo/s8.aiff", 110.3, 1.0),
    ("vo/s9.aiff", 125.3, 1.0),
    ("vo/s10.aiff", 138.3, 1.0),
]


def run(cmd):
    subprocess.run(cmd, check=True)


def seg_filter(crop, speed):
    pts = f"setpts=(PTS-STARTPTS)/{speed}," if speed != 1 else "setpts=PTS-STARTPTS,"
    if crop == "push":
        return (f"{pts}fps={FPS},scale=1920:1080:flags=lanczos,"
                f"zoompan=z='1+0.08*on/{10 * FPS}':x='iw/2-(iw/zoom/2)':y='ih*0.55-(ih/zoom*0.55)':d=1:s=1920x1080:fps={FPS}")
    if crop == "phone":
        return (f"{pts}fps={FPS},scale=-2:1000:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0d0d0d,"
                f"fade=t=out:st=11.5:d=0.5")
    x, y, w, h = crop
    return f"{pts}fps={FPS},crop={w}:{h}:{x}:{y},scale=1920:1080:flags=lanczos"


def pdf_still(png, out, frames, top_fraction):
    # Fit the page width to 1080 px, centred on a grey desk; slow scroll down the page
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(HERE / png), "-frames:v", str(frames),
         "-vf", (f"scale=1100:-2,crop=1100:1080:0:'(ih-1080)*{top_fraction}+n*1.2',"
                 f"pad=1920:1080:(ow-iw)/2:0:color=0x6b7280,fps={FPS},format=yuv420p"),
         "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "16", str(out)])


def main():
    parts, total_frames = [], 0
    for i, (src, t_in, t_out, crop, speed) in enumerate(SEGMENTS):
        out = OUT / f"seg{i:02d}.mp4"
        frames = round((t_out - t_in) / speed * FPS)
        total_frames += frames
        if src.startswith("PDF"):
            pdf_still("pdf_1.png" if src == "PDF1" else "pdf_2.png", out, frames, 0.0 if src == "PDF1" else 0.05)
        else:
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t_in:.2f}", "-i", SRC[src],
                 "-vf", seg_filter(crop, speed) + ",format=yuv420p", "-frames:v", str(frames),
                 "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-r", str(FPS), str(out)])
        parts.append(out)
    print("frames", total_frames, "=", total_frames / FPS, "s")
    assert total_frames == 150 * FPS, total_frames

    (OUT / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(OUT / "list.txt"),
         "-c", "copy", str(OUT / "picture.mp4")])

    # Captions: small white text on a dark pill, bottom-left
    draws = []
    for a, b, text in CAPTIONS:
        t = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
        draws.append(f"drawtext=fontfile={FONT}:text='{t}':fontsize=30:fontcolor=white:box=1:boxcolor=0x111111@0.72:"
                     f"boxborderw=16:x=48:y=h-96:enable='between(t,{a},{b})'")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "picture.mp4"), "-vf", ",".join(draws),
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", str(OUT / "captioned.mp4")])

    # Audio: place every clip at its time, mix, normalise
    inputs, chains = [], []
    for i, (f, start, tempo) in enumerate(AUDIO):
        inputs += ["-i", str(HERE / f)]
        tempo_f = f"atempo={tempo}," if tempo != 1.0 else ""
        chains.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,{tempo_f}adelay={int(start * 1000)}:all=1[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(AUDIO)))
    fc = ";".join(chains) + f";{mix}amix=inputs={len(AUDIO)}:normalize=0,apad,atrim=0:150,loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", "[out]", "-ar", "48000",
         "-c:a", "aac", "-b:a", "192k", str(OUT / "audio.m4a")])

    final = HERE / "AquaSentinel_demo.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "captioned.mp4"), "-i", str(OUT / "audio.m4a"),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-t", "150", "-movflags", "+faststart", str(final)])
    print("wrote", final)


if __name__ == "__main__":
    main()
