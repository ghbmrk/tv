/* Original synthetic ARM fixture; never linked into the TV product. */
__attribute__((noinline)) int native_probe_range(unsigned value) {
    return value < 4 ? (int)(value * 3 + 7) : -1;
}
