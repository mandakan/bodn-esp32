# bodn/sounds.py — UI sound design system
#
# Named sound presets for consistent audio feedback across all screens.
# Each sound is a list of (freq_hz, duration_ms, wave) steps played in sequence.
# Use AudioEngine.play_sound(name) to trigger them.

SOUNDS = {
    # Navigation — short high-frequency tick, percussive and consistent
    "nav_click": [(2400, 12, "sine")],
    # Select — rising chirp when entering a mode
    "select": [(660, 60, "sine"), (880, 80, "sine")],
    # Back — descending tone when leaving a screen
    "back": [(660, 60, "sine"), (440, 80, "sine")],
    # Correct answer — bright ascending
    "correct": [(660, 80, "sine"), (880, 120, "sine")],
    # Wrong answer — low flat buzz
    "wrong": [(220, 250, "square")],
    # Generic UI feedback (button press, toggle)
    "boop": [(440, 100, "sine")],
    # Startup — "To-to-ro, To-to-ro" from My Neighbor Totoro chorus
    # Melody: G4-G4-E4 (×2), rhythm at ~120 BPM: eighth-eighth-dotted quarter
    "start": [
        (392, 200, "sine"),  # To-    (G4, eighth)
        (392, 200, "sine"),  # -to-   (G4, eighth)
        (330, 450, "sine"),  # -ro    (E4, dotted quarter — held)
        (0, 100, "sine"),  #        (breath)
        (392, 200, "sine"),  # To-    (G4, eighth)
        (392, 200, "sine"),  # -to-   (G4, eighth)
        (330, 600, "sine"),  # -ro    (E4, half — final hold)
    ],
    # Level up / puzzle complete — triumphant
    "complete": [(660, 100, "sine"), (880, 100, "sine"), (1100, 150, "sine")],
    # Timer warning — urgent double beep
    "warning": [(880, 80, "sine"), (0, 60, "sine"), (880, 80, "sine")],
    # Rule switch (Rule Follow game)
    "rule_switch": [(587, 200, "sine")],
}
