def detect_language(text: str) -> str:
    """
    Detects language based on character set analysis:
    - Devanagari script mapping -> hi_in (Hindi)
    - Arabic script mapping -> ar_eg (Arabic)
    - Latin alphabet mapping -> en_us (English)
    """
    counts = {"en_us": 0, "hi_in": 0, "ar_eg": 0}
    for char in text:
        cp = ord(char)
        if 0x0900 <= cp <= 0x097F:
            counts["hi_in"] += 1
        elif 0x0600 <= cp <= 0x06FF:
            counts["ar_eg"] += 1
        elif (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):
            counts["en_us"] += 1
            
    max_lang = max(counts, key=counts.get)
    if counts[max_lang] > 0:
        return max_lang
    return "en_us"  # Fallback default
