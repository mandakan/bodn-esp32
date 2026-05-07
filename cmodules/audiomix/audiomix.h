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

// Per-voice ring buffer for SRC_RINGBUF (streamed WAV) sources. The buffer
// must be large enough to ride out the longest stall of the Python feeder
// task on core 1 -- i.e. the worst slow frame from rendering, GC, or SD
// contention. 8192 bytes = 256 ms at 16 kHz mono 16-bit, comfortably
// above the 80-200 ms slow frames seen during scenario transitions.
// PSRAM cost: 16 voices × 8 KB = 128 KB (negligible on the 8 MB part).
#define AUDIOMIX_RINGBUF_SIZE   8192
#define AUDIOMIX_MONO_BUF_SIZE  512   // bytes per mono read (256 samples = 16ms)

// Scope tap: post-mix mono samples captured for visualisation.
// 512 samples × 2 bytes = 1 KB; at 16 kHz that's 32 ms of history
// (~2 cycles of the lowest pentatonic tone the UI shows).
#define AUDIOMIX_SCOPE_SAMPLES  512

// Waveform types (match Python: 0=square, 1=sine, 2=sawtooth, 3=noise,
//                                4=triangle, 5=noise_pitched)
#define AUDIOMIX_WAVE_SQUARE         0
#define AUDIOMIX_WAVE_SINE           1
#define AUDIOMIX_WAVE_SAWTOOTH       2
#define AUDIOMIX_WAVE_NOISE          3
#define AUDIOMIX_WAVE_TRIANGLE       4
#define AUDIOMIX_WAVE_NOISE_PITCHED  5

// Default per-voice gain (fixed-point 16.16) — ~70%
#define AUDIOMIX_GAIN_DEFAULT       45875

// Fade length in samples
#define AUDIOMIX_FADE_SAMPLES   16  // 1ms @ 16kHz

// Source-swap crossfade length: BUFFER → BUFFER swaps overlap the old
// source's fade-out with the new source's fade-in over this many samples
// using equal-power (cos²/sin²) weights. 80 samples = 5 ms at 16 kHz —
// long enough that the brain stops perceiving a transition, short enough
// to feel instantaneous.
#define AUDIOMIX_XFADE_SAMPLES  80

// Waveform crossfade length (samples) for phase-preserving tone_wave swaps.
// 48 ≈ 3ms at 16kHz — short enough to feel "instant", long enough to mask
// the sample-value jump between differently-shaped oscillators.
#define AUDIOMIX_WAVE_XFADE_SAMPLES   48

// Stutter-gate edge ramp in samples (linear slew on the binary on/off gate).
// 24 ≈ 1.5ms @ 16kHz — removes the click without audibly softening the gate.
#define AUDIOMIX_STUTTER_RAMP_SAMPLES 24

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
    volatile uint8_t  fade_in;          // apply fade-in on first chunk (WAV/legacy)
    volatile uint8_t  fade_out;         // 1 = fade out this chunk then stop
    volatile uint8_t  writing;          // 1 = Python is writing fields, clock must skip

    // SRC_RINGBUF fields
    audiomix_ringbuf_t ringbuf;
    volatile uint8_t eof;               // Python sets when file data is exhausted

    // SRC_TONE fields
    uint32_t tone_freq;
    uint32_t tone_samples_left;
    uint32_t tone_phase;                // Q16 cycle phase (0..65535 = one cycle)
    uint16_t tone_lfsr;                 // LFSR state for AUDIOMIX_WAVE_NOISE_PITCHED
    uint8_t  tone_wave;                 // currently rendering waveform
    uint8_t  tone_sustain;              // 1 = play indefinitely until stop_req

    // Waveform crossfade: when Python asks for a wave change via
    // voice_set_wave(), we keep playing tone_wave while linearly mixing in
    // tone_wave_pending over AUDIOMIX_WAVE_XFADE_SAMPLES samples.  0 = idle.
    uint8_t  tone_wave_pending;
    uint16_t tone_wave_xfade_left;

    // --- Reusable modulation layer (any SRC_TONE voice) ---
    // All fields zero = effect disabled.  Modes enable a subset and all
    // stack: vibrato + tremolo + stutter run simultaneously on one voice.

    // Pitch LFO (vibrato)
    uint16_t mod_lfo_pitch_rate_cHz;    // 0 = off; 500 = 5.00 Hz
    int16_t  mod_lfo_pitch_depth_cents; // ± cents; 30 = a quarter-tone wobble
    uint32_t mod_lfo_pitch_phase;       // Q16 phase accumulator

    // Amplitude LFO (tremolo)
    uint16_t mod_lfo_amp_rate_cHz;      // 0 = off
    uint16_t mod_lfo_amp_depth_q15;     // 0..32767 fraction of gain to wobble
    uint32_t mod_lfo_amp_phase;

    // Pitch bend ramp (hold-to-slide)
    int32_t  mod_bend_cents_per_s;      // 0 = off; sign = direction
    int32_t  mod_bend_current_cents;    // accumulated (clamped to ±limit)
    int32_t  mod_bend_limit_cents;      // absolute clamp; 0 = no clamp

    // Stutter gate (amp chopped to 0 at duty cycle)
    uint16_t mod_stutter_rate_cHz;      // 0 = off
    uint16_t mod_stutter_duty_q15;      // 0..32767 = off-fraction of cycle
    uint32_t mod_stutter_phase;
    uint16_t mod_stutter_gate_q15;      // smoothed 0/32767 gate (slew-limited)

    // Envelope state (for clock-driven tone tracks — replaces fade_in for tones)
    uint32_t env_attack_samples;        // attack ramp length (0 = instant)
    uint32_t env_release_samples;       // release ramp length
    uint32_t env_total_samples;         // total note duration (0 = legacy fade path)
    uint32_t env_pos;                   // current position in envelope
    uint8_t  env_velocity;              // 0-127 volume scaling

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

    // Pending source — captured by Python when swapping a BUFFER/TONE
    // source on a held voice. Two activation paths:
    //   - xfade_samples_left > 0: equal-power crossfade with the current
    //     source over xfade_samples_total samples (BUFFER → BUFFER only).
    //   - fade_out = 1: sequential 1 ms fade-out of the current source,
    //     then immediate activation of pending (used for any → TONE and
    //     for TONE → BUFFER, where simultaneous read of both sources
    //     would be more code than the seam is worth).
    // SRC_NONE in pending_source = no pending swap.
    volatile audiomix_source_t pending_source;
    volatile uint8_t  pending_loop;
    const uint8_t    *pending_buf_ptr;
    uint32_t          pending_buf_len;
    volatile uint32_t pending_buf_pos;     // mixer advances during crossfade
    uint32_t          pending_tone_freq;
    uint32_t          pending_tone_samples;
    uint8_t           pending_tone_wave;
    volatile uint32_t xfade_samples_left;  // 0 = no crossfade in progress
    uint32_t          xfade_samples_total; // for weight = i/total mapping

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
    uint8_t perc_mask;                  // percussion: which tracks fire (bitmask, bits 0-4)
    uint16_t melody_freq;               // DEPRECATED — use tone tracks; kept for compat
} seq_step_t;

// Percussion track config: pointer to pre-loaded PCM buffer
typedef struct {
    const uint8_t *buf_ptr;
    uint32_t buf_len;
} seq_perc_track_t;

// Per-step tone parameters (synth note definition)
typedef struct {
    uint16_t freq;                      // Hz (0 = rest / silent)
    uint16_t duration_ms;               // note length
    uint8_t  wave;                      // AUDIOMIX_WAVE_*
    uint8_t  attack_ms;                 // envelope attack (0 = instant click)
    uint8_t  release_ms;                // envelope release tail-off
    uint8_t  velocity;                  // volume 0-127
} seq_tone_step_t;                      // 8 bytes, naturally aligned

// Tone track: a voice slot + per-step tone data, triggered by the clock
#define SEQ_MAX_TONE_TRACKS 3           // melody + metronome + spare

typedef struct {
    uint8_t  voice_idx;                 // which mixer voice this track drives
    uint16_t step_mask;                 // bitmask: which steps are active (bits 0-15)
    seq_tone_step_t steps[SEQ_MAX_STEPS]; // per-step tone parameters
} seq_tone_track_t;

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

    // Voice mapping: which voice index to use for each perc track
    uint8_t perc_voice[SEQ_MAX_PERC_TRACKS];

    // DEPRECATED melody fields — kept for backward compat with clock_set_melody()
    uint8_t melody_voice;               // voice index for melody
    uint16_t melody_duration_ms;        // tone duration (default 150)
    uint8_t  melody_wave;               // waveform type (default SINE)

    // Tone tracks (clock-driven synth notes — replaces melody for new code)
    seq_tone_track_t tone_tracks[SEQ_MAX_TONE_TRACKS];

    // Anti-double-trigger: sample count when each track was last manually
    // triggered.  Indices 0..4 = perc tracks, 5..7 = tone tracks.
    uint32_t manual_trigger_sample[SEQ_MAX_PERC_TRACKS + SEQ_MAX_TONE_TRACKS];
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

    // Scope tap — post-mix mono samples for visualisation.
    // Mixer writes a full chunk at once, then advances scope_wr.  Python reads
    // the most recent N samples via scope_peek() (memcpy — race-free for the
    // reader because writes arrive in bounded chunks, not mid-byte).
    int16_t  scope_buf[AUDIOMIX_SCOPE_SAMPLES];
    volatile uint32_t scope_wr;         // next write sample index (monotonic)

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
