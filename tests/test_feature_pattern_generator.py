import pytest
from core.pattern_generator import generate_urls_from_pattern

def test_pattern_generator_number_ranges():
    # Padded number range
    urls = generate_urls_from_pattern("https://example.com/file_[01-05].zip")
    assert urls == [
        "https://example.com/file_01.zip",
        "https://example.com/file_02.zip",
        "https://example.com/file_03.zip",
        "https://example.com/file_04.zip",
        "https://example.com/file_05.zip",
    ]

    # Non-padded number range with step
    urls_step = generate_urls_from_pattern("https://example.com/img_[1-7:2].jpg")
    assert urls_step == [
        "https://example.com/img_1.jpg",
        "https://example.com/img_3.jpg",
        "https://example.com/img_5.jpg",
        "https://example.com/img_7.jpg",
    ]

def test_pattern_generator_letter_ranges():
    # Lowercase letters
    urls_lower = generate_urls_from_pattern("https://example.com/part_[a-d].rar")
    assert urls_lower == [
        "https://example.com/part_a.rar",
        "https://example.com/part_b.rar",
        "https://example.com/part_c.rar",
        "https://example.com/part_d.rar",
    ]

    # Uppercase letters with step 2
    urls_upper = generate_urls_from_pattern("https://example.com/volume_[A-E:2].iso")
    assert urls_upper == [
        "https://example.com/volume_A.iso",
        "https://example.com/volume_C.iso",
        "https://example.com/volume_E.iso",
    ]

def test_pattern_generator_placeholders():
    # Explicit start, end, digits
    urls = generate_urls_from_pattern(
        "https://example.com/photo_(*).png",
        start=8,
        end=11,
        digits=3
    )
    assert urls == [
        "https://example.com/photo_008.png",
        "https://example.com/photo_009.png",
        "https://example.com/photo_010.png",
        "https://example.com/photo_011.png",
    ]

def test_pattern_generator_edge_cases():
    # Empty string
    assert generate_urls_from_pattern("") == []
    # No pattern
    assert generate_urls_from_pattern("https://example.com/single.mp4") == ["https://example.com/single.mp4"]
    # Reverse range
    urls_rev = generate_urls_from_pattern("https://example.com/cd_[3-1].bin")
    assert urls_rev == [
        "https://example.com/cd_3.bin",
        "https://example.com/cd_2.bin",
        "https://example.com/cd_1.bin",
    ]

