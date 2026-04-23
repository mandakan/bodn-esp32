#define MICROPY_HW_BOARD_NAME               "Bodn ESP32-S3"
#define MICROPY_HW_MCU_NAME                 "ESP32S3"

// Olimex DevKit-Lipo uses external USB-UART, not native USB.
#define MICROPY_HW_ENABLE_UART_REPL         (1)

#define MICROPY_HW_I2C0_SCL                 (9)
#define MICROPY_HW_I2C0_SDA                 (8)

// --- Size trimming ---
// Both of these are `#ifndef`-gated in mpconfigport.h so overriding here
// wins. Paired with the matching IDF-level disables in sdkconfig.board so
// neither the Python bindings nor the C stack gets compiled.
#define MICROPY_PY_BLUETOOTH                (0)
#define MICROPY_PY_ESPNOW                   (0)

// Stock ESP32 ROM level (EXTRA_FEATURES) only enables deflate
// decompression; FULL_FEATURES is needed for DeflateIO.write. The web
// UI precomputes HTML_GZ at import time to cut ~25 KB off every page
// load over WiFi — without this the fallback serves raw HTML.
#define MICROPY_PY_DEFLATE_COMPRESS         (1)
