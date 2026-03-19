import streamlit as st
import google.genai as genai
from google.genai import types # Memperbaiki NameError: types
import os
import time
import asyncio
import edge_tts
import re

# --- 1. PEMBERSIHAN FILE (Mencegah OSError) ---
# Menghapus file sisa proses sebelumnya agar tidak bentrok
files_to_clean = ["temp.mp4", "res.mp4", "vo.mp3", "final.mp4"]
for f in files_to_clean:
    if os.path.exists(f):
        try:
            os.remove(f)
        except:
            pass # Mengabaikan jika file sedang terkunci sistem

# --- 2. SETUP MOVIEPY (Kompatibilitas Versi 2.0+) ---
try:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    import moviepy.video.fx as vfx
except ImportError:
    st.error("Gagal memuat MoviePy. Pastikan requirements.txt sudah benar.")
    st.stop()

st.set_page_config(page_title="AI Video Automator", layout="centered")

def init_gemini():
    try:
        return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    except Exception as e:
        st.error(f"API Key Error: {e}")
        return None

async def generate_voice(text, output_path, voice_name):
    communicate = edge_tts.Communicate(text, voice_name)
    await communicate.save(output_path)

# --- 3. UI SIDEBAR (Definisi Variabel) ---
with st.sidebar:
    st.header("⚙️ Pengaturan")
    lang = st.selectbox("Bahasa", ["Indonesia", "Inggris"])
    
    if lang == "Indonesia":
        voice_option = st.radio("Pilih Suara", ["Pria (Ardi)", "Wanita (Gadis)"])
        v_name = "id-ID-ArdiNeural" if "Pria" in voice_option else "id-ID-GadisNeural"
    else:
        voice_option = st.radio("Pilih Suara", ["Pria (Guy)", "Wanita (Ava)"])
        v_name = "en-US-GuyNeural" if "Pria" in voice_option else "en-US-AvaNeural"
    
    style = st.text_input("Gaya Bahasa", "Energik & Persuasif")
    goal = st.text_input("Tujuan Video", "Review Produk")
    # Memastikan extra_cmd didefinisikan agar tidak NameError
    extra_cmd = st.text_area("Instruksi Tambahan (CTA)", "")

st.title("🎬 AI Video Automation")
uploaded_file = st.file_uploader("Upload Video", type=["mp4", "mov", "mpeg4"])

# --- 4. LOGIKA PROSES UTAMA ---
if uploaded_file and st.button("🚀 Mulai Proses"):
    g_client = init_gemini()
    if g_client:
        res_p, aud_p, out_p = "res.mp4", "vo.mp3", "final.mp4"

        with st.status("Memproses...", expanded=True) as status:
            # A. RESIZING
            st.write("🔧 Resizing Video...")
            with open("temp.mp4", "wb") as f:
                f.write(uploaded_file.read())
            
            clip = VideoFileClip("temp.mp4")
            dur = clip.duration # Simpan durasi asli
            
            # Resize menggunakan standar v2.0
            clip_res = clip.with_effects([vfx.Resize(height=720)])
            clip_res.write_videofile(res_p, codec="libx264", audio=False)

            # --- 2. GEMINI ANALYSIS (Sinkronisasi Durasi) ---
            st.write("🧠 Menganalisis Video & Membuat Naskah Pas...")
            v_upload = g_client.files.upload(file=res_p)
            while v_upload.state.name == "PROCESSING":
                time.sleep(2)
                v_upload = g_client.files.get(name=v_upload.name)
            
            # LOGIKA DURASI:
            # Kita beri jeda 3 detik di awal video agar visual terlihat dulu.
            # Sisa waktu bicara = total durasi - 3 detik.
            target_dur = max(dur - 3.0, 1.0)
            
            # BATAS KATA: Rata-rata 2.1 kata per detik (Kecepatan Normal-Energik)
            # Contoh: Video 10 detik -> Sisa 7 detik -> Maks 14-15 kata.
            word_limit = int(target_dur * 2.1)

            prompt_text = f"""
            Buat naskah {goal} {lang} dengan gaya {style}.
            
            INSTRUKSI KETAT:
            1. Narasi HARUS selesai dibaca dalam {target_dur:.1f} detik.
            2. Gunakan MAKSIMAL {word_limit} kata saja.
            3. JANGAN tulis label 'Narasi:', 'Naskah:', atau durasi waktu (00:00).
            4. LANGSUNG mulai pada kata pertama naskah.
            5. CTA: {extra_cmd}
            """
            
            response = g_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[types.Content(role="user", parts=[
                    types.Part.from_uri(file_uri=v_upload.uri, mime_type=v_upload.mime_type),
                    types.Part.from_text(text=prompt_text)
                ])]
            )
            
            # Pembersihan Teks dari label sampah agar tidak dibaca Voiceover
            narasi = re.sub(r'Narasi:|Naskah:|Script:|\d{2}:\d{2}', '', response.text).strip()
            st.info(f"Naskah ({len(narasi.split())} kata): {narasi}")

            # --- 3. VOICE GENERATION ---
            st.write("🎙️ Membuat Voiceover...")
            asyncio.run(generate_voice(narasi, aud_p, v_name))

            # --- 4. MERGING (Kunci Durasi & Jeda) ---
            if os.path.exists(aud_p):
                st.write("🎬 Menggabungkan Video & Audio...")
                a_clip = AudioFileClip(aud_p)
                
                # Suara baru masuk di detik ke-3.0
                a_clip = a_clip.with_start(3.0)
                
                try:
                    # Gabungkan audio dan video
                    final = clip_res.with_audio(a_clip)
                    
                    # PENTING: Paksa durasi final sama dengan video asli (dur)
                    # Ini mencegah error "Accessing time t > duration"
                    final = final.with_duration(dur)
                    
                    final.write_videofile(out_p, codec="libx264", audio_codec="aac")
                    status.update(label="✅ Berhasil!", state="complete")
                except Exception as e:
                    st.error(f"Gagal saat penggabungan: {e}")
                    st.stop()

        # --- 5. HASIL AKHIR ---
        st.divider()
        if os.path.exists(out_p):
            st.video(out_p)
            with open(out_p, "rb") as f:
                st.download_button("💾 Download Video", f, "hasil_ai.mp4", "video/mp4")
