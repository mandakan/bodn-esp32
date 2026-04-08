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

#define AUDIOMIX_NUM_VOICES     16

#define AUDIOMIX_RINGBUF_SIZE   2048  // bytes per voice (64ms @ 16kHz mono 16-bit)
#define AUDIOMIX_MONO_BUF_SIZE  512   // bytes per mono read (256 samples = 16ms)

// Waveform types (match Python: 0=square, 1=sine, 2=sawtooth, 3=noise)
#define AUDIOMIX_WAVE_SQUARE    0
#define AUDIOMIX_WAVE_SINE      1
#define AUDIOMIX_WAVE_SAWTOOTH  2
#define AUDIOMIX_WAVE_NOISE     3

// Default per-voice gain (fixed-point 16.16) — ~70%
#define AUDIOMIX_GAIN_DEFAULT       45875

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
    volatile uint8_t  stop_req;         // Python sets 1; core 0 clears + stops
    volatile uint8_t  fade_in;          // apply fade-in on first chunk
    volatile uint8_t  writing;          // 1 = Python is writing fields, clock must skip

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
// Step sequencer clock (sample-accurate grid triggering)
// ---------------------------------------------------------------------------

#define SEQ_MAX_STEPS       16
#define SEQ_MAX_PERC_TRACKS 5
#define SEQ_ANTI_REPEAT_MS  50   // suppress grid trigger if voice played within this window

// Per-step trigger: what to play when the playhead crosses this step
typedef struct {
    // Percussion: which tracks are active (bitmask, bits 0-4)
    uint8_t perc_mask;
    // Melody: frequency in Hz (0 = off)
    uint16_t melody_freq;
} seq_step_t;

// Percussion track config: pointer to pre-loaded PCM buffer
typedef struct {
    const uint8_t *buf_ptr;
    uint32_t buf_len;
} seq_perc_track_t;

typedef struct {
    // Clock state
    volatile uint8_t  playing;          // 1 = clock running
    volatile uint8_t  n_steps;          // 8 or 16
    volatile uint8_t  current_step;     // 0..n_steps-1 (core 0 writes, Python reads)
    uint32_t samples_per_step;          // computed from BPM + sample_rate
    uint32_t sample_count;              // accumulator within current step

    // Grid data (Python writes, core 0 reads)
    seq_step_t steps[SEQ_MAX_STEPS];

    // Percussion track buffers (set once by Python)
    seq_perc_track_t perc_tracks[SEQ_MAX_PERC_TRACKS];

    // Voice mapping: which voice index to use for each track
    uint8_t perc_voice[SEQ_MAX_PERC_TRACKS];  // voice index for each perc track
    uint8_t melody_voice;               // voice index for melody

    // Melody config
    uint16_t melody_duration_ms;        // tone duration for melody notes (default 150)
    uint8_t  melody_wave;               // waveform type (default SINE)

    // Anti-double-trigger: sample count when each track/melody was last
    // manually triggered (by button preview).  Indexed by perc track (0-4)
    // + melody (index 5).
    uint32_t manual_trigger_sample[SEQ_MAX_PERC_TRACKS + 1];
    uint32_t total_samples;             // monotonic sample counter for anti-repeat

    // BPM for Python query
    volatile uint16_t bpm;
} seq_clock_t;

// ---------------------------------------------------------------------------
// Global state
// ---------------------------------------------------------------------------

typedef struct {
    audiomix_voice_t voices[AUDIOMIX_NUM_VOICES];
    volatile uint32_t master_volume;    // 0–100
    volatile uint32_t vol_mult;         // precomputed fixed-point multiplier
    volatile uint8_t  running;          // 1 = mix task active
    uint32_t sample_rate;
    uint32_t seq_counter;               // monotonic counter for voice age

    // Step sequencer clock
    seq_clock_t clock;

    // Diagnostics (written by core 0, read by Python)
    volatile uint32_t underruns;        // ring buffer underrun count
    volatile uint32_t mix_calls;        // total mix loop iterations
    volatile uint32_t mix_us_last;      // last mix cycle duration (µs)
    volatile uint32_t mix_us_max;       // worst-case mix cycle (µs)
    volatile uint32_t mix_us_sum;       // accumulated mix time for averaging
    volatile uint32_t mix_avg_count;    // number of samples in sum
    volatile uint32_t active_voices;    // voices active in last mix cycle
    volatile uint32_t task_stack_hwm;   // FreeRTOS high water mark (bytes)
    volatile uint32_t dma_wait_us;      // last DMA write blocking time (µs)
} audiomix_state_t;

// Global state (allocated once by init)
extern audiomix_state_t *audiomix_state;

#endif // AUDIOMIX_H
