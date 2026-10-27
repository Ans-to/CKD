"""End-to-end Blender render, local Kokoro narration, mix, and QC report.

All visible imagery is created in nokia_documentary_15m.py. Audio is locally
synthesized/procedural, mixed to measured targets, then imported into Blender's
Video Sequence Editor for final mux and encode.
"""
from __future__ import annotations

import json, math, os, re, shutil, subprocess, sys, tempfile, wave
from pathlib import Path

import numpy as np
import bpy
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[2]
SPEC=json.loads((ROOT/"scripts/blender/nokia_documentary_15m.json").read_text())
OUT=Path(os.environ.get("NOKIA_OUTPUT_DIR",ROOT/"output/nokia-documentary" )).resolve()
FPS=int(SPEC["fps"]); W,H=SPEC["resolution"]; PREVIEW=int(os.environ.get("NOKIA_PREVIEW_SECONDS","0")); DURATION=float(PREVIEW or 900); SCENES=SPEC["scenes"] if not PREVIEW else SPEC["scenes"][:1]; SR=48000
FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()


def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2500:])
    return p


def write_mono(path, audio, sr):
    a=np.clip(np.asarray(audio,dtype=np.float32),-1,1)
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((a*32767).astype("<i2").tobytes())


def write_silence_stereo(path,seconds,sr=SR):
    frames=round(seconds*sr)
    with wave.open(str(path),"wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(bytes(frames*4))


def synthesize_narration(work):
    from ckd.voice.kokoro_engine import KokoroEngine
    engine=KokoroEngine("am_michael",speed=1.05,allow_download=True)
    raw=[]; sample_rate=24000
    def sentence_chunks(text):
        sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",text) if x.strip()]
        out=[]
        for sentence in sentences:
            words=sentence.split()
            if len(words)<=30:
                out.append(sentence)
            else:
                clauses=re.split(r"(?<=[,;:—])\s+",sentence)
                buf=""
                for clause in clauses:
                    if buf and len((buf+" "+clause).split())>26:
                        out.append(buf); buf=clause
                    else: buf=(buf+" "+clause).strip()
                if buf: out.append(buf)
        return out
    for i,entry in enumerate(SCENES):
        chunks=[]
        for sentence in sentence_chunks(entry["narration"]):
            res=engine.synthesize(sentence,"en")
            a=np.asarray(res.audio,dtype=np.float32).reshape(-1)
            sr=int(getattr(res,"sample_rate",sample_rate) or sample_rate)
            if sr!=sample_rate:
                tmp=work/f"voice-{i:02d}-resampled.wav"
                write_mono(tmp,a,sr)
                out=work/f"voice-{i:02d}.wav"
                run([FFMPEG,"-y","-v","error","-i",str(tmp),"-ar",str(sample_rate),"-ac","1",str(out)])
                with wave.open(str(out),"rb") as r: a=np.frombuffer(r.readframes(r.getnframes()),dtype="<i2").astype(np.float32)/32768
            chunks.append(a)
        gap=np.zeros(round(0.16*sample_rate),dtype=np.float32)
        joined=[]
        for j,chunk in enumerate(chunks):
            joined.append(chunk)
            if j<len(chunks)-1: joined.append(gap)
        a=np.concatenate(joined) if joined else np.zeros(0,dtype=np.float32)
        raw.append(a)
        print(f"Synthesized scene {i+1:02d}/13 ({len(a)/sample_rate:.1f}s from {len(chunks)} clauses)",flush=True)
    raw_total=sum(len(a) for a in raw)/sample_rate
    gap_seconds=0.75
    target_speech=DURATION-gap_seconds*(len(raw)-1)-5.0
    tempo=raw_total/target_speech
    if not 0.82<=tempo<=1.28:
        raise RuntimeError(f"Narration duration {raw_total:.1f}s requires implausible time stretch {tempo:.3f}; revise script.")
    voice_parts=[]; durations=[]
    for i,a in enumerate(raw):
        src=work/f"narration-{i:02d}-raw.wav"; dst=work/f"narration-{i:02d}-fit.wav"
        write_mono(src,a,sample_rate)
        run([FFMPEG,"-y","-v","error","-i",str(src),"-af",f"atempo={tempo:.6f}","-ar",str(sample_rate),"-ac","1",str(dst)])
        with wave.open(str(dst),"rb") as r: data=np.frombuffer(r.readframes(r.getnframes()),dtype="<i2").astype(np.float32)/32768
        voice_parts.append(data); durations.append(len(data)/sample_rate)
        if i < len(raw)-1: voice_parts.append(np.zeros(round(gap_seconds*sample_rate),dtype=np.float32))
    voice=np.concatenate(voice_parts)
    voice_path=work/"narration-continuous.wav"; write_mono(voice_path,voice,sample_rate)
    # Dialogue tone/dynamics first; target -16 LUFS and -6 dBTP leaves room for score.
    voice48=work/"narration-mastered.wav"
    run([FFMPEG,"-y","-v","error","-i",str(voice_path),"-af","highpass=f=80,acompressor=threshold=0.04:ratio=3:attack=8:release=140:knee=5,loudnorm=I=-16:TP=-6:LRA=7","-ar",str(SR),"-ac","2","-c:a","pcm_s24le",str(voice48)])
    # Scene boundaries use measured post-time-stretch narration durations and the planned short music bridges.
    timings=[]; cursor=0.0
    for i,d in enumerate(durations):
        span=d+(gap_seconds if i<len(durations)-1 else 5.0)
        timings.append({"start_seconds":cursor,"duration_seconds":span,"speech_seconds":d})
        cursor+=span
    (work/"timings.json").write_text(json.dumps({"scenes":timings,"duration_seconds":DURATION,"fps":FPS},indent=2))
    return voice48


def synthesize_music(work):
    """Create an original, low-level ambient bed from oscillators; no audio asset is downloaded."""
    path=work/"procedural-score.wav"; sr=SR; seconds=int(DURATION)
    # Chunk writing keeps memory bounded for a 15-minute stereo track.
    with wave.open(str(path),"wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        for start in range(0,seconds,10):
            n=min(10,seconds-start)*sr
            t=(np.arange(n,dtype=np.float64)/sr)+start
            chord_idx=(t//22).astype(int)%6
            bases=np.array([55.0,65.41,73.42,82.41,98.0,73.42])[chord_idx]
            fade=np.minimum(1.0,np.minimum((t+1)/4,0.16+0.84*np.clip((seconds-t)/8,0,1))).clip(0,1)
            slow=0.65+0.35*np.sin(2*np.pi*t/19.0)
            mono=(0.32*np.sin(2*np.pi*bases*t)+0.18*np.sin(2*np.pi*bases*1.5*t+0.4)+0.12*np.sin(2*np.pi*bases*2.0*t+1.2))*slow*fade
            stereo=np.column_stack((mono,mono*0.94+0.02*np.sin(2*np.pi*(bases+0.5)*t)))
            stereo=np.clip(stereo,-0.9,0.9)
            w.writeframes((stereo*32767).astype("<i2").tobytes())
    return path


def mix_and_measure(voice, music, work):
    mix=work/"master-mix.wav"
    ducked=work/"music-ducked.wav"
    duck_filter="sidechaincompress=threshold=0.04:ratio=3.5:attack=35:release=650:makeup=1"
    fc=("[0:a]asplit=2[voice][side];[1:a]volume=-6dB[bed];"
        f"[bed][side]{duck_filter}[ducked];"
        "[voice][ducked]amix=inputs=2:duration=longest:normalize=0,"
        "loudnorm=I=-14:TP=-1:LRA=8[mix]")
    run([FFMPEG,"-y","-v","error","-i",str(voice),"-i",str(music),"-filter_complex",fc,
         "-map","[mix]","-t",str(DURATION),"-ar",str(SR),"-ac","2","-c:a","pcm_s24le",str(mix)])
    duck_fc=f"[1:a]volume=-6dB[bed];[bed][0:a]{duck_filter}[ducked]"
    run([FFMPEG,"-y","-v","error","-i",str(voice),"-i",str(music),"-filter_complex",duck_fc,
         "-map","[ducked]","-t",str(DURATION),"-ar",str(SR),"-ac","2","-c:a","pcm_s24le",str(ducked)])
    return mix,ducked


def render_visuals(work,preview_seconds=0):
    sys.path.insert(0,str(ROOT/"scripts/blender"))
    import nokia_documentary_15m as visual
    timings=work/"timings.json"
    out=work/"blender-visuals.mp4"
    frames=visual.build(str(timings),str(out),preview_seconds)
    return out,frames


def blender_mux(visual,mix,output,frames):
    final=bpy.data.scenes.new("Blender VSE final assembly")
    final.render.resolution_x=W; final.render.resolution_y=H; final.render.resolution_percentage=100
    final.render.fps=FPS; final.frame_start=1; final.frame_end=frames
    editor=final.sequence_editor_create()
    strips=editor.strips
    movie=strips.new_movie("Blender procedural visual source",str(visual),channel=1,frame_start=1)
    # Six-fps procedural frames are blended to the 30-fps delivery inside Blender VSE.
    visual_info=next(imageio_ffmpeg.read_frames(str(visual),pix_fmt="rgb24"))
    movie.transform.scale_x=W/visual_info["size"][0]
    movie.transform.scale_y=H/visual_info["size"][1]
    speed=strips.new_effect(name="Blender frame-interpolated visual motion",type="SPEED",channel=2,
                            frame_start=1,frame_end=frames,input1=movie)
    # A fivefold slow-down maps the six-fps source timeline to the 30-fps output;
    # Blender's interpolator synthesizes the in-between frames from adjacent renders.
    speed.speed_control="MULTIPLY"
    speed.speed_factor=0.2
    speed.use_frame_interpolate=True
    sound=strips.new_sound("Narration + ducked procedural score",str(mix),channel=3,frame_start=1)
    final.render.use_sequencer=True
    final.render.image_settings.file_format="FFMPEG"
    final.render.ffmpeg.format="MPEG4"; final.render.ffmpeg.codec="H264"
    final.render.ffmpeg.constant_rate_factor="HIGH"; final.render.ffmpeg.ffmpeg_preset="GOOD"
    final.render.ffmpeg.audio_codec="AAC"; final.render.ffmpeg.audio_bitrate=192
    final.render.filepath=str(output); final.render.use_file_extension=True
    # Blender's sequencer performs the final audio/video assembly and encode.
    bpy.ops.render.render(animation=True,scene=final.name)


def quality_report(path,frames,work,voice_path,music_source_path,ducked_music_path):
    reader=imageio_ffmpeg.read_frames(str(path),pix_fmt="rgb24")
    info=next(reader); count=0; black=[]
    for i,frame in enumerate(reader):
        count+=1
        a=np.frombuffer(frame,dtype=np.uint8).reshape(H,W,3)[::12,::12]
        if a.max()<8 or a.std()<0.5: black.append(i)
    if count!=frames: raise RuntimeError(f"decoded frame count mismatch: {count} != {frames}")
    if black: raise RuntimeError(f"possible black-screen frames: {black[:10]}")
    # ebur128 reports integrated loudness and true peak; the report is parsed from FFmpeg output.
    p=subprocess.run([FFMPEG,"-hide_banner","-nostats","-i",str(path),"-af","ebur128=peak=true","-f","null","-"],capture_output=True,text=True)
    import re
    im=re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS",p.stderr)
    tp=re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS",p.stderr)
    integrated=float(im[-1]) if im else None; true_peak=float(tp[-1]) if tp else None
    sd=subprocess.run([FFMPEG,"-hide_banner","-nostats","-i",str(path),"-af","silencedetect=noise=-60dB:d=0.5","-f","null","-"],capture_output=True,text=True)
    silence_starts=[float(x) for x in re.findall(r"silence_start: ([0-9.]+)",sd.stderr)]
    silence_ends=[float(x) for x in re.findall(r"silence_end: ([0-9.]+)",sd.stderr)]
    silence_spans=[]
    for j,st in enumerate(silence_starts):
        en=silence_ends[j] if j<len(silence_ends) else float(info["duration"])
        if en-st>0.5: silence_spans.append([round(st,2),round(en,2)])
    # Measure narration, original score, and sidechain-reduced score separately.
    def measure_volume(audio_path):
        proc=subprocess.run([FFMPEG,"-hide_banner","-nostats","-i",str(audio_path),"-af","volumedetect","-f","null","-"],capture_output=True,text=True)
        mean=re.search(r"mean_volume: (-?\d+(?:\.\d+)?) dB",proc.stderr)
        peak=re.search(r"max_volume: (-?\d+(?:\.\d+)?) dB",proc.stderr)
        return (float(mean.group(1)) if mean else None,float(peak.group(1)) if peak else None)
    raw_music_mean,raw_music_peak=measure_volume(music_source_path)
    ducked_mean,ducked_peak=measure_volume(ducked_music_path)
    preduck_mean=raw_music_mean-6.0 if raw_music_mean is not None else None
    reduction=preduck_mean-ducked_mean if preduck_mean is not None and ducked_mean is not None else None
    music_stats={"procedural_score_source_mean_dbfs":raw_music_mean,"procedural_score_source_sample_peak_dbfs":raw_music_peak,"score_preduck_mean_dbfs":preduck_mean,"music_under_voice_mean_dbfs":ducked_mean,"music_under_voice_sample_peak_dbfs":ducked_peak,"measured_sidechain_reduction_db":reduction}
    voice_stats={}
    for key,filter_name in (("voice_loudness","ebur128=peak=true"),("voice_levels","volumedetect")):
        proc=subprocess.run([FFMPEG,"-hide_banner","-nostats","-i",str(voice_path),"-af",filter_name,"-f","null","-"],capture_output=True,text=True)
        if key=="voice_loudness":
            il=re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS",proc.stderr); pk=re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS",proc.stderr)
            voice_stats.update({"narration_integrated_lufs":float(il[-1]) if il else None,"narration_true_peak_dbfs":float(pk[-1]) if pk else None})
        else:
            av=re.search(r"mean_volume: (-?\d+(?:\.\d+)?) dB",proc.stderr); mx=re.search(r"max_volume: (-?\d+(?:\.\d+)?) dB",proc.stderr)
            voice_stats.update({"narration_average_dbfs":float(av.group(1)) if av else None,"narration_sample_peak_dbfs":float(mx.group(1)) if mx else None})
    level_ok=integrated is not None and abs(integrated-(-14.0))<=0.6
    peak_ok=true_peak is not None and true_peak<=-0.9
    music_level_ok=ducked_mean is not None and abs(ducked_mean-(-28.0))<=4.0
    report={"file":str(path),"duration_seconds":info["duration"],"fps":info["fps"],"size":info["size"],"decoded_frames":count,"expected_frames":frames,"video_codec":info["codec"],"audio_codec":info["audio_codec"],"integrated_lufs":integrated,"true_peak_dbtp":true_peak,"narration_measurements":voice_stats,"ducked_music_measurements":music_stats,"music_level_target_pass":music_level_ok,"possible_black_frame_samples":black,"silence_intervals_over_0_5s":silence_spans,"integrated_loudness_target_pass":level_ok,"true_peak_target_pass":peak_ok,"status":"PASS" if count==frames and not black and not silence_spans and level_ok and peak_ok and music_level_ok else "FAIL"}
    if report["status"]!="PASS": raise RuntimeError(f"QC failed: {report}")
    (work/"quality-report.json").write_text(json.dumps(report,indent=2))
    return report


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    preview=PREVIEW
    print(f"Render mode: preview={preview}s, audio duration={DURATION:g}s, {FPS} fps at {W}x{H} delivery",flush=True)
    with tempfile.TemporaryDirectory(prefix="nokia-blender-") as td:
        work=Path(td)
        if preview:
            # A short silent visual-only preflight validates Blender/Eevee and composition
            # quickly; the complete run below generates all narration, music and final QC.
            timings={"scenes":[{"start_seconds":0,"duration_seconds":preview,"speech_seconds":0}],"duration_seconds":preview,"fps":FPS}
            (work/"timings.json").write_text(json.dumps(timings))
            visual,source_frames=render_visuals(work,preview)
            final=OUT/f"nokia-documentary-{int(DURATION)}s-preview.mp4"
            final_frames=round(DURATION*FPS)
            silence=work/"silent-preflight.wav"; write_silence_stereo(silence,DURATION)
            blender_mux(visual,silence,final,final_frames)
            reader=imageio_ffmpeg.read_frames(str(final),pix_fmt="rgb24"); info=next(reader); count=0; black=[]
            for i,frame in enumerate(reader):
                count+=1
                vw,vh=info["size"]
                a=np.frombuffer(frame,dtype=np.uint8).reshape(vh,vw,3)[::12,::12]
                if a.max()<8 or a.std()<0.5: black.append(i)
            if count!=final_frames or black: raise RuntimeError(f"Visual preflight failed: decoded={count}, expected={final_frames}, black={black[:10]}")
            report={"file":str(final),"duration_seconds":info["duration"],"fps":info["fps"],"size":info["size"],"decoded_frames":count,"expected_frames":final_frames,"video_codec":info["codec"],"source_visual_frames":source_frames,"source_visual_fps":6,"audio_status":"silent track only; narration/music are omitted in this visual preflight","possible_black_frame_samples":black,"status":"PASS"}
            (OUT/"quality-report.json").write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2),flush=True)
            return
        voice=synthesize_narration(work); music=synthesize_music(work); mix,ducked_music=mix_and_measure(voice,music,work)
        # The Blender scene builder reads the actual Kokoro timing map from this temporary run.
        visual,source_frames=render_visuals(work,0)
        final=OUT/"nokia-documentary-15m.mp4"
        final_frames=round(DURATION*FPS)
        blender_mux(visual,mix,final,final_frames)
        report=quality_report(final,final_frames,OUT,voice,music,ducked_music)
        report["source_visual_frames"]=source_frames
        report["source_visual_fps"]=6
        (OUT/"quality-report.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)

if __name__=="__main__": main()
