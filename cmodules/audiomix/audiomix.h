// audiomix.h — shared types and constants for the Bodn audio mixer
//
// Native C audio engine running on ESP32-S3 core 1.  The mixer task
// owns the I2S peripheral and runs independently of the MicroPython VM.
// Python controls playback by writing to shared voice state structs.

#ifndef AUDIOMIX_H
#define AUDIOMIX_H

#include <stdint.h>
#include <stdbool.h>

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

#define AUDIOMIX_NUM_VOICES     6
#define AUDIOMIX_V_MUSIC        0
#define AUDIOMIX_V_SFX_BASE     1
#define AUDIOMIX_V_SFX_END      5   // exclusive
#define AUDIOMIX_V_UI           5

#define AUDIOMIX_RINGBUF_SIZE   2048  // bytes per voice (64ms @ 16kHz mono 16-bit)
#define AUDIOMIX_MONO_BUF_SIZE  512   // bytes per mono read (256 samples = 16ms)

// Waveform types (match Python: 0=square, 1=sine, 2=sawtooth, 3=noise)
#define AUDIOMIX_WAVE_SQUARE    0
#define AUDIOMIX_WAVE_SINE      1
#define AUDIOMIX_WAVE_SAWTOOTH  2
#define AUDIOMIX_WAVE_NOISE     3

// Per-voice gain presets (fixed-point 16.16)
#define AUDIOMIX_GAIN_MUSIC         45875   // 70%
#define AUDIOMIX_GAIN_MUSIC_DUCKED  16384   // 25%
#define AUDIOMIX_GAIN_SFX           45875   // 70%
#define AUDIOMIX_GAIN_UI            52428   // 80%

// Fade length in samples
#define AUDIOMIX_FADE_SAMPLES   16  // 1ms @ 16kHz

// ---------------------------------------------------------------------------
// Ring buffer (lock-free SPSC)
// ---------------------------------------------------------------------------

typedef struct {
    uint8_t *buf;               // allocated buffer (power-of-2 size)
    uint32_t size;              // buffer size in bytes (must be power of 2)
    volatile uint32_t wr;       // write index (core 0 / Python)
    volatile uint32_t rd;       // read index (core 1 / mixer)
} audiomix_ringbuf_t;

// ---------------------------------------------------------------------------
// Voice source types
// ---------------------------------------------------------------------------

typedef enum {
    SRC_NONE     = 0,   // voice inactive
    SRC_RINGBUF  = 1,   // WAV data streamed from Python via ring buffer
    SRC_TONE     = 2,   // procedural tone (generated on core 1)
    SRC_SEQUENCE = 3,   // sequence of tones (generated on core 1)
    SRC_BUFFER   = 4,   // zero-copy playback from pre-loaded bytearray
} audiomix_source_t;

// ---------------------------------------------------------------------------
// Voice state
// ---------------------------------------------------------------------------

// Packed sequence step: freq (u16) + duration_ms (u16) + wave (u8) = 5 bytes
#define AUDIOMIX_SEQ_STEP_SIZE  5
#define AUDIOMIX_SEQ_MAX_STEPS  51  // 255 / 5

typedef struct {
    volatile audiomix_source_t source_type;
    volatile uint32_t gain;             // fixed-point 16.16 multiplier
    volatile uint8_t  loop;             // 1 = loop, 0 = one-shot
    volatile uint8_t  is_music;         // 1 = music voice (subject to ducking)
    volatile uint8_t  stop_req;         // Python sets 1; core 1 clears + stops
    volatile uint8_t  fade_in;          // apply fade-in on first chunk

    // SRC_RINGBUF fields
    audiomix_ringbuf_t ringbuf;
    volatile uint8_t eof;               // Python sets when file data is exhausted

    // SRC_TONE fields
    uint32_t tone_freq;
    uint32_t tone_samples_left;
    uint32_t tone_phase;
    uint8_t  tone_wave;

    // SRC_SEQUENCE fields
    uint8_t  seq_buf[AUDIOMIX_SEQ_MAX_STEPS * AUDIOMIX_SEQ_STEP_SIZE];
    volatile uint8_t  seq_n_steps;
    volatile uint8_t  seq_current;
    uint32_t seq_samples_left;
    uint32_t seq_phase;

    // SRC_BUFFER fields (zero-copy from Python bytearray)
    const uint8_t *buf_ptr;             // pointer into PSRAM
    uint32_t buf_len;                   // total bytes
    volatile uint32_t buf_pos;          // current read offset (core 1 advances)

    // Age tracking for voice stealing
    volatile uint32_t start_seq;
} audiomix_voice_t;

// ---------------------------------------------------------------------------
// Global mixer state
// ---------------------------------------------------------------------------

typedef struct {
    audiomix_voice_t voices[AUDIOMIX_NUM_VOICES];
    volatile uint32_t master_volume;    // 0–100
    volatile uint32_t vol_mult;         // precomputed fixed-point multiplier
    volatile uint8_t  running;          // 1 = mix task active
    volatile uint32_t underruns;        // diagnostic: ring buffer underrun count
    uint32_t sample_rate;
    uint32_t seq_counter;               // monotonic counter for voice age
} audiomix_state_t;

// Global state (allocated once by init)
extern audiomix_state_t *audiomix_state;

#endif // AUDIOMIX_H
